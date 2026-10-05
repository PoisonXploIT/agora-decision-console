"""agora_serve - servicio FastAPI de AGORA.

Endpoints:

- GET    /health             -> {"ok": true, ...}
- GET    /backends           -> fichas BackendInfo de los backends registrados
- POST   /v1/decide          -> Decision (un backend; por defecto 'mock')
- POST   /v1/decide/compare  -> Decision por backend + acuerdo entre ellos
- GET    /v1/packs           -> packs cargados (F5: agora_serve/packs.py)
- GET    /v1/runs            -> historial de decisiones en memoria
- DELETE /v1/runs            -> limpia el historial

La respuesta JSON conserva el orden de insercion de las probabilidades
(orden canonico de criterios): nunca sort_keys.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agora_core.schemas import (  # noqa: F401
    BackendInfo,
    Decision,
    DecisionRequest,
    Question,
)
from agora_adapters import MockAdapter


class DecideBody(BaseModel):
    request: DecisionRequest = Field(description="pregunta + estado")


class CompareBody(BaseModel):
    question: Any
    state: Any = None
    backends: list[str] | None = Field(
        default=None, description="nombres de backend; por defecto todos"
    )


def create_app() -> FastAPI:
    app = FastAPI(title="AGORA", version="0.0.1")
    registry: dict[str, Any] = {"mock": MockAdapter()}
    runs: list[dict] = []

    # Backends opcionales por entorno. Sin nube por defecto. LAYA local viene activo salvo
    # AGORA_LAYAA=0; Eikos y JEV solo si se les da URL.
    if os.environ.get("AGORA_LAYAA", "1") != "0":
        try:
            from agora_adapters import LayaAdapter

            registry["laya"] = LayaAdapter(
                base_url=os.environ.get("AGORA_LAYAA_URL", "http://127.0.0.1:8787"),
                api_key=os.environ.get("LAYA_API_KEY") or None,
            )
        except Exception:  # noqa: BLE001
            pass
    if os.environ.get("AGORA_EIKOS_URL"):
        try:
            from agora_adapters import EikosAdapter

            registry["eikos"] = EikosAdapter(base_url=os.environ["AGORA_EIKOS_URL"])
        except Exception:  # noqa: BLE001
            pass
    if os.environ.get("AGORA_JEV_URL"):
        try:
            from agora_adapters import JevAdapter

            registry["jev"] = JevAdapter(base_url=os.environ["AGORA_JEV_URL"])
        except Exception:  # noqa: BLE001
            pass

    def register(name: str, adapter: Any) -> None:
        registry[name] = adapter

    app.state.registry = registry
    app.state.runs = runs

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "agora", "backends": list(registry)}

    @app.get("/backends")
    def backends() -> dict:
        return {
            "backends": [registry[n].info().model_dump() for n in registry]
        }

    @app.post("/v1/decide", response_model=Decision)
    def decide(body: DecisionRequest) -> Decision:
        name = (body.backend or "mock").lower()
        if name not in registry:
            raise HTTPException(
                status_code=404,
                detail=f"backend desconocido {name!r}; disponibles: {sorted(registry)}",
            )
        t0 = time.monotonic()
        try:
            decision = registry[name].decide(body)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(e)) from e
        runs.append(
            {
                "ts": time.time(),
                "backend": name,
                "question_id": body.question.id,
                "type": decision.type.value,
                "probabilities": dict(decision.probabilities),
                "expected": decision.expected,
                "action": decision.action,
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 3),
            }
        )
        return decision

    @app.post("/v1/decide/compare")
    def compare(body: CompareBody) -> dict:
        question = (
            Question.model_validate(body.question)
            if isinstance(body.question, dict)
            else body.question
        )
        names = [n.lower() for n in body.backends] if body.backends else list(registry)
        unknown = [n for n in names if n not in registry]
        if unknown:
            raise HTTPException(
                status_code=404, detail=f"backends desconocidos: {unknown}"
            )
        results: dict[str, Decision] = {}
        errors: dict[str, str] = {}
        for name in names:
            req = DecisionRequest(
                state=body.state if body.state is not None else {},
                question=question,
                backend=name,
            )
            try:
                d = registry[name].decide(req)
            except Exception as e:  # noqa: BLE001
                errors[name] = str(e)
                continue
            results[name] = d
            runs.append(
                {
                    "ts": time.time(),
                    "backend": name,
                    "question_id": question.id,
                    "type": d.type.value,
                    "probabilities": dict(d.probabilities),
                    "expected": d.expected,
                    "action": d.action,
                    "latency_ms": 0.0,
                }
            )
        if not results:
            raise HTTPException(status_code=502, detail={"errors": errors})
        return {
            "question_id": question.id,
            "results": results,
            "errors": errors,
            "agreement": _agreement(results),
        }

    @app.get("/v1/packs")
    def packs() -> dict:
        try:
            from .packs import list_packs  # F5
        except ImportError:
            return {"packs": []}

        return {"packs": [p.model_dump() for p in list_packs()]}

    @app.get("/v1/runs")
    def get_runs(limit: int = 50) -> dict:
        return {"count": len(runs), "runs": runs[-max(1, limit):]}

    @app.delete("/v1/runs")
    def clear_runs() -> dict:
        n = len(runs)
        runs.clear()
        return {"cleared": n}

    ui_dir = Path(__file__).resolve().parent.parent / "agora_ui"
    if ui_dir.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount(
            "/ui",
            StaticFiles(directory=str(ui_dir), html=True),
            name="ui",
        )

    return app


def _agreement(results: dict[str, Decision]) -> dict:
    """Acuerdo simple entre backends: argmax comun."""
    if len(results) < 2:
        return {"backends": list(results), "acuerdo_argmax": None}
    votes: dict[str, int] = {}
    for d in results.values():
        best = max(d.probabilities.values())
        for k, v in d.probabilities.items():
            if v == best:
                votes[k] = votes.get(k, 0) + 1
    top = sorted(k for k, c in votes.items() if c == len(results))
    return {"backends": list(results), "acuerdo_argmax": top or None}


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8800)


if __name__ == "__main__":
    main()
