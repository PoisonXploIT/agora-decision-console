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


class BackendConfig(BaseModel):
    """Alta de un backend en caliente (local o API). La clave vive solo en memoria."""

    name: str = Field(min_length=1)
    kind: str = "http"  # mock | http (compatible TypeSafe: LAYA local, JEV API, Eikos serve)
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


class FromTextBody(BaseModel):
    text: str = Field(min_length=1, description="instruccion en lenguaje natural")
    type: str | None = Field(default=None, description="tipo preferido: choice | score | noul")


# Catalogo de modelos conocidos: local (sin clave) o API cloud (con clave).
CATALOG = [
    {
        "name": "laya",
        "label": "LAYAA v2 (local, CPU)",
        "kind": "http",
        "base_url": "http://127.0.0.1:8787",
        "needs_key": False,
        "privacy": "local",
    },
    {
        "name": "eikos-4b",
        "label": "Eikos-4B (local, GPU)",
        "kind": "http",
        "base_url": "http://127.0.0.1:8901",
        "needs_key": False,
        "privacy": "local",
    },
    {
        "name": "jev",
        "label": "JEV / TypeSafe (cloud, API)",
        "kind": "http",
        "base_url": "https://api.typesafe.ai",
        "needs_key": True,
        "privacy": "cloud",
    },
    {
        "name": "mock",
        "label": "Mock (falso, sin modelo)",
        "kind": "mock",
        "base_url": None,
        "needs_key": False,
        "privacy": "local",
    },
]


def create_app() -> FastAPI:
    app = FastAPI(title="AGORA", version="0.0.1")
    registry: dict[str, Any] = {"mock": MockAdapter()}
    runs: list[dict] = []
    from agora_serve import store

    def build(cfg: dict) -> Any:
        """Crea un adaptador a partir de una config {name,kind,base_url,api_key,model}."""
        kind = str(cfg.get("kind") or "http").strip().lower()
        name = str(cfg.get("name") or "").strip().lower()
        if kind == "mock":
            adapter: Any = MockAdapter()
        else:
            # LAYA local, JEV API y Eikos serve hablan la misma API compatible TypeSafe.
            from agora_adapters import LayaAdapter

            adapter = LayaAdapter(
                base_url=cfg.get("base_url") or "http://127.0.0.1:8787",
                api_key=cfg.get("api_key") or None,
                model=cfg.get("model") or None,
            )
        if name:
            adapter.name = name
        return adapter

    # 1) Backends persistidos (los que se configuraron en la UI).
    for cfg in store.load():
        try:
            registry[cfg["name"].strip().lower()] = build(cfg)
        except Exception:  # noqa: BLE001
            pass

    # 2) Por entorno: LAYA local activo salvo AGORA_LAYAA=0 (si no esta ya persistido).
    if os.environ.get("AGORA_LAYAA", "1") != "0" and "laya" not in registry:
        try:
            registry["laya"] = build(
                {
                    "name": "laya",
                    "kind": "http",
                    "base_url": os.environ.get("AGORA_LAYAA_URL", "http://127.0.0.1:8787"),
                    "api_key": os.environ.get("LAYA_API_KEY") or None,
                }
            )
        except Exception:  # noqa: BLE001
            pass
    if os.environ.get("AGORA_EIKOS_URL") and "eikos" not in registry:
        try:
            registry["eikos"] = build(
                {"name": "eikos", "kind": "http", "base_url": os.environ["AGORA_EIKOS_URL"]}
            )
        except Exception:  # noqa: BLE001
            pass

    def register(name: str, adapter: Any) -> None:
        registry[name] = adapter

    app.state.registry = registry
    app.state.runs = runs

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "agora", "backends": list(registry)}

    @app.get("/catalog")
    def catalog() -> dict:
        return {"catalog": CATALOG}

    @app.get("/backends")
    def backends() -> dict:
        return {
            "backends": [registry[n].info().model_dump() for n in registry]
        }

    @app.post("/backends")
    def add_backend(cfg: BackendConfig) -> dict:
        """Registra un backend en caliente y lo PERSISTE en el perfil del usuario."""
        name = cfg.name.strip().lower()
        if not name:
            raise HTTPException(status_code=422, detail="nombre requerido")
        kind = (cfg.kind or "http").strip().lower()
        if kind not in ("mock", "http", "typesafe", "laya", "eikos", "jev"):
            raise HTTPException(status_code=422, detail=f"kind desconocido: {kind!r}")
        try:
            adapter = build(
                {
                    "name": name,
                    "kind": kind,
                    "base_url": cfg.base_url,
                    "api_key": cfg.api_key,
                    "model": cfg.model,
                }
            )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"no se pudo crear el backend: {e}") from e
        registry[name] = adapter
        store.upsert(
            {
                "name": name,
                "kind": "mock" if kind == "mock" else "http",
                "base_url": cfg.base_url,
                "api_key": cfg.api_key,
                "model": cfg.model,
            }
        )
        info = adapter.info().model_dump()
        info["name"] = name
        return {"ok": True, "backend": info, "backends": list(registry), "persistido": True}

    @app.delete("/backends/{name}")
    def del_backend(name: str) -> dict:
        name = name.strip().lower()
        if name == "mock":
            raise HTTPException(status_code=422, detail="mock no se puede quitar")
        if name not in registry:
            raise HTTPException(status_code=404, detail="backend no registrado")
        registry.pop(name, None)
        store.remove(name)
        return {"ok": True, "backends": list(registry)}

    @app.post("/v1/questions/from-text")
    def question_from_text(body: FromTextBody) -> dict:
        """Convierte una instruccion en lenguaje natural en una pregunta tipada."""
        from agora_serve.questions import ChatError, from_text

        try:
            q = from_text(body.text, default_type=body.type or "choice")
        except ChatError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {"question": q.model_dump()}

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
