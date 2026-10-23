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

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from agora_adapters import MockAdapter
from agora_core.schemas import (  # noqa: F401
    BackendInfo,
    Decision,
    DecisionRequest,
    Question,
)
from agora_serve import integrations, logging_setup, runs_db, security


class DecideBody(BaseModel):
    request: DecisionRequest = Field(description="pregunta + estado")


class CompareBody(BaseModel):
    question: Any
    state: Any = None
    backends: list[str] | None = Field(
        default=None, max_length=10, description="nombres de backend; por defecto todos"
    )


class BackendConfig(BaseModel):
    """Alta de un backend en caliente (local o API). La clave vive solo en memoria."""

    name: str = Field(min_length=1, max_length=32, pattern="^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    kind: str = "http"  # mock | http (compatible TypeSafe: LAYA local, JEV API, Eikos serve)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=512)
    model: str | None = Field(default=None, max_length=128)

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, v: str | None) -> str | None:
        if v is None or not str(v).strip():
            return None
        return security.validate_backend_url(str(v))


class PackBody(BaseModel):
    pack: str = Field(min_length=1, max_length=80)
    state: Any = None
    backends: list[str] | None = Field(default=None, max_length=10)


class ReplayBody(BaseModel):
    backend: str | None = Field(default=None, max_length=40)


class StopBody(BaseModel):
    confirm: bool = Field(default=False, description="true para matar el proceso")


class FromTextBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000,
                      description="instruccion en lenguaje natural")
    type: str | None = Field(default=None, description="tipo preferido: choice | score | noul")


class ReportBody(BaseModel):
    title: str | None = None
    state: Any = None
    pack: str | None = Field(default=None, description="nombre del pack a evaluar")
    questions: list[Any] | None = Field(default=None, max_length=50,
                                        description="preguntas sueltas")
    backends: list[str] | None = None


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
        "model": "jev-1.13.0",
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
    {
        # No es un modelo de decision: es el LLM de chat que traduce lenguaje natural a JSON.
        "name": "chat",
        "label": "LLM de chat :8099 (genera el JSON desde texto)",
        "kind": "chat",
        "base_url": "http://127.0.0.1:8099",
        "needs_key": False,
        "privacy": "local",
    },
]


MAX_STATE_BYTES = 64_000
MAX_STORED_STATE_BYTES = 8_000


def _stored_state(state: Any) -> Any:
    """Estado que se guarda para replay: solo si es pequeno."""
    try:
        blob = json.dumps(state, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return state if len(blob) <= MAX_STORED_STATE_BYTES else None


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _check_state_size(state: Any) -> None:
    try:
        blob = json.dumps(state, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"state no serializable: {e}") from e
    if len(blob) > MAX_STATE_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"state demasiado grande ({len(blob)} bytes; max {MAX_STATE_BYTES})")


def _decision_event(backend: str, question: Any, decision: Any) -> dict:
    return {
        "backend": backend,
        "question_id": getattr(question, "id", None),
        "type": getattr(getattr(decision, "type", None), "value", None),
        "probabilities": dict(getattr(decision, "probabilities", {}) or {}),
        "expected": getattr(decision, "expected", None),
        "action": getattr(decision, "action", None),
        "latency_ms": getattr(getattr(decision, "trace", None), "latency_ms", None),
    }


def _save_run(item: dict) -> None:
    """Guarda una decision en el historial SQLite."""
    runs_db.insert(item)


def create_app() -> FastAPI:
    app = FastAPI(title="AGORA", version="0.0.1")
    security.install(app)
    logging_setup.setup_logging()
    app.state.log = logging_setup.get_logger()
    registry: dict[str, Any] = {"mock": MockAdapter()}
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
        nombre = str(cfg.get("name") or "").strip().lower()
        try:
            if not re.match(r"^[a-z0-9][a-z0-9_.-]{0,31}$", nombre):
                raise ValueError(f"nombre invalido: {nombre!r}")
            if cfg.get("base_url"):
                security.validate_backend_url(str(cfg["base_url"]))
            registry[nombre] = build(cfg)
        except Exception as e:  # noqa: BLE001
            app.state.log.warning("backend persistido descartado %s: %s", nombre or "?", e)

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

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "agora", "backends": list(registry)}

    @app.get("/catalog")
    def catalog() -> dict:
        from agora_serve import models as m

        out = []
        for c in CATALOG:
            st = m.status(c["name"])
            out.append({**c, **{k: st[k] for k in ("configurado", "starter", "probe", "up")}})
        return {"catalog": out}

    @app.post("/models/{name}/start")
    def model_start(name: str) -> dict:
        from agora_serve import models as m

        try:
            return {"ok": True, **m.start(name.strip().lower())}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.post("/models/{name}/stop")
    def model_stop(name: str, body: StopBody) -> dict:
        from agora_serve import models as m

        if not body.confirm:
            raise HTTPException(
                status_code=428,
                detail="confirmacion requerida: envia {\"confirm\": true}; se matara el proceso "
                       "que escuche en el puerto del modelo",
            )
        try:
            return {"ok": True, **m.stop(name.strip().lower())}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.get("/models/{name}/log")
    def model_log(name: str, lines: int = 40) -> dict:
        from agora_serve import models as m

        return m.tail(name.strip().lower(), max(1, min(500, lines)))

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

    @app.delete("/backends/{name}/key")
    def delete_backend_key(name: str) -> dict:
        name = name.strip().lower()
        if name not in registry:
            raise HTTPException(status_code=404, detail="backend no registrado")
        adapter = registry[name]
        if hasattr(adapter, "api_key"):
            adapter.api_key = ""
        store.remove_key(name)
        return {"ok": True, "backends": list(registry)}

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
        from agora_serve.questions import ChatError, chat_info, from_text

        try:
            q = from_text(body.text, default_type=body.type or "choice")
        except ChatError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {"question": q.model_dump(), "generado_por": chat_info()}

    def _resolve_questions(body: ReportBody) -> list[Question]:
        qs: list[Question] = []
        if body.questions:
            qs = [Question.model_validate(x) for x in body.questions]
        elif body.pack:
            from agora_serve.packs import list_packs

            p = next((x for x in list_packs() if x.name == body.pack), None)
            if p is None:
                raise HTTPException(status_code=404, detail=f"pack desconocido: {body.pack!r}")
            qs = [
                Question(id=q.id, type=q.type, prompt=q.prompt, criteria=q.criteria)
                for q in p.questions
            ]
        if not qs:
            raise HTTPException(status_code=422, detail="hace falta 'pack' o 'questions'")
        return qs

    @app.post("/v1/report/preview")
    def report_preview(body: ReportBody) -> dict:
        """Resumen de lo que incluiria el informe, sin generar el PDF."""
        qs = _resolve_questions(body)
        names = [n.lower() for n in body.backends] if body.backends else list(registry)
        names = [n for n in names if n in registry]
        if not names:
            raise HTTPException(status_code=422, detail="sin backends validos")
        return {
            "pack": body.pack,
            "question_count": len(qs),
            "backend_count": len(names),
            "backends": names,
            "questions": [{"id": q.id, "type": q.type.value, "prompt": q.prompt[:120]}
                          for q in qs[:20]],
            "title": body.title or "Informe de decisiones",
        }

    @app.post("/v1/report")
    def report(body: ReportBody):
        """Informe PDF de un pack (o preguntas sueltas) sobre varios backends."""
        from datetime import datetime

        from fastapi.responses import Response

        from agora_serve.report import build_pdf

        qs = _resolve_questions(body)

        names = [n.lower() for n in body.backends] if body.backends else list(registry)
        names = [n for n in names if n in registry]
        if not names:
            raise HTTPException(status_code=422, detail="sin backends validos")

        state = body.state if body.state is not None else {}
        results = []
        for q in qs:
            by = []
            for n in names:
                req = DecisionRequest(state=state, question=q, backend=n)
                try:
                    d = registry[n].decide(req)
                    by.append({
                        "backend": n,
                        "model": d.trace.model,
                        "latency_ms": d.trace.latency_ms,
                        "probabilities": dict(d.probabilities),
                        "expected": d.expected,
                        "action": d.action,
                    })
                except Exception as e:  # noqa: BLE001
                    by.append({"backend": n, "error": str(e), "probabilities": {}})
            results.append({
                "question_id": q.id,
                "prompt": q.prompt,
                "type": q.type.value,
                "by_backend": by,
            })

        estado_txt = ""
        try:
            estado_txt = json.dumps(state, ensure_ascii=False)
        except Exception:
            estado_txt = str(state)
        if len(estado_txt) > 90:
            estado_txt = estado_txt[:87] + "..."

        pdf = build_pdf(
            title=body.title or "Informe de decisiones",
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            results=results,
            backends=names,
            state_label=estado_txt,
        )
        base = body.pack or body.title or "informe"
        slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:40] or "informe"
        app.state.log.info("report pack=%s q=%d backends=%s", body.pack, len(qs), names)
        integrations.emit("report", {"pack": body.pack, "questions": len(qs), "backends": names})
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="agora-{slug}.pdf"'},
        )

    @app.post("/v1/decide", response_model=Decision)
    def decide(body: DecisionRequest) -> Decision:
        _check_state_size(body.state)
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
            app.state.log.warning("decide fallo backend=%s: %s", name, e)
            raise HTTPException(status_code=502, detail=str(e)) from e
        app.state.log.info("decide backend=%s q=%s", name, body.question.id)
        integrations.emit("decide", _decision_event(name, body.question, decision))
        _save_run({
            "id": _new_run_id(),
            "ts": time.time(),
            "backend": name,
            "question_id": body.question.id,
            "question": body.question.model_dump(),
            "state": _stored_state(body.state),
            "type": decision.type.value,
            "probabilities": dict(decision.probabilities),
            "expected": decision.expected,
            "action": decision.action,
            "latency_ms": round((time.monotonic() - t0) * 1000.0, 3),
        })
        return decision

    @app.post("/v1/decide/compare")
    def compare(body: CompareBody) -> dict:
        _check_state_size(body.state)
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
            _save_run({
                "id": _new_run_id(),
                "ts": time.time(),
                "backend": name,
                "question_id": question.id,
                "question": question.model_dump(),
                "state": _stored_state(body.state),
                "type": d.type.value,
                "probabilities": dict(d.probabilities),
                "expected": d.expected,
                "action": d.action,
                "latency_ms": 0.0,
            })
        app.state.log.info("compare backends=%s ok=%d err=%d", names, len(results), len(errors))
        integrations.emit("compare", {
            "question_id": question.id,
            "agreement": _agreement(results),
            "results": {n: _decision_event(n, question, d) for n, d in results.items()},
            "errors": errors,
        })
        if not results:
            raise HTTPException(status_code=502, detail={"errors": errors})
        return {
            "question_id": question.id,
            "results": results,
            "errors": errors,
            "agreement": _agreement(results),
        }

    @app.post("/v1/decide/pack")
    def decide_pack(body: PackBody) -> dict:
        """Decisiones de todas las preguntas de un pack. Pensado para integraciones."""
        _check_state_size(body.state)
        qs = _resolve_questions(ReportBody(pack=body.pack, state=body.state))
        names = [n.lower() for n in body.backends] if body.backends else list(registry)
        names = [n for n in names if n in registry]
        if not names:
            raise HTTPException(status_code=422, detail="sin backends validos")
        state = body.state if body.state is not None else {}
        out = []
        errors: dict[str, str] = {}
        for q in qs:
            by = {}
            for n in names:
                req = DecisionRequest(state=state, question=q, backend=n)
                try:
                    d = registry[n].decide(req)
                except Exception as e:  # noqa: BLE001
                    errors[f"{q.id}/{n}"] = str(e)
                    by[n] = {"error": str(e)}
                    continue
                by[n] = _decision_event(n, q, d)
                _save_run({"id": _new_run_id(), "ts": time.time(), "backend": n,
                           "question_id": q.id, "question": q.model_dump(),
                           "state": _stored_state(state), "type": d.type.value,
                           "probabilities": dict(d.probabilities),
                           "expected": d.expected, "action": d.action,
                           "latency_ms": float(d.trace.latency_ms or 0.0)})
            out.append({"question_id": q.id, "prompt": q.prompt, "type": q.type.value,
                        "by_backend": by})
        app.state.log.info("pack %s q=%d backends=%s", body.pack, len(qs), names)
        integrations.emit("decide", {"pack": body.pack, "questions": len(qs),
                                     "backends": names, "errors": errors})
        return {"pack": body.pack, "backends": names, "results": out, "errors": errors}

    @app.get("/v1/integrations")
    def integrations_status() -> dict:
        return {"webhooks": integrations.status(),
                "api_keys": len(security.api_keys())}

    @app.get("/v1/packs")
    def packs() -> dict:
        try:
            from .packs import list_packs  # F5
        except ImportError:
            return {"packs": []}

        return {"packs": [p.model_dump() for p in list_packs()]}

    @app.get("/v1/runs")
    def get_runs(limit: int = 50, offset: int = 0, backend: str | None = None) -> dict:
        total, items = runs_db.list_runs(limit=limit, offset=offset, backend=backend)
        return {"count": total, "runs": items}

    @app.delete("/v1/runs/{run_id}")
    def delete_run(run_id: str) -> dict:
        if not runs_db.delete(run_id):
            raise HTTPException(status_code=404, detail=f"run desconocido: {run_id}")
        app.state.log.info("run borrado %s", run_id)
        return {"ok": True, "deleted": run_id, "count": runs_db.count()}

    @app.delete("/v1/runs")
    def clear_runs() -> dict:
        n = runs_db.clear()
        app.state.log.warning("historial vaciado (%d runs)", n)
        return {"cleared": n}

    @app.post("/v1/runs/{run_id}/replay", response_model=Decision)
    def replay_run(run_id: str, body: ReplayBody) -> Decision:
        """Repite una decision guardada con el backend original o el indicado."""
        row = runs_db.get(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"run desconocido: {run_id}")
        q = row.get("question")
        if not q:
            raise HTTPException(status_code=409,
                                detail="este run no guardo la pregunta (estado grande o version antigua)")
        name = (body.backend or row.get("backend") or "mock").lower()
        if name not in registry:
            raise HTTPException(status_code=404, detail=f"backend desconocido: {name}")
        req = DecisionRequest(state=row.get("state") or {},
                              question=Question.model_validate(q), backend=name)
        try:
            d = registry[name].decide(req)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(e)) from e
        _save_run({
            "id": _new_run_id(),
            "ts": time.time(),
            "backend": name,
            "question_id": req.question.id,
            "question": req.question.model_dump(),
            "state": _stored_state(req.state),
            "type": d.type.value,
            "probabilities": dict(d.probabilities),
            "expected": d.expected,
            "action": d.action,
            "latency_ms": round(float(d.trace.latency_ms or 0.0), 3),
            "replay_of": run_id,
        })
        app.state.log.info("replay %s backend=%s", run_id, name)
        integrations.emit("replay", {"replay_of": run_id, **_decision_event(name, req.question, d)})
        return d

    @app.get("/v1/logs")
    def logs(lines: int = 80) -> dict:
        return {"lines": logging_setup.tail(max(1, min(500, lines)))}

    ui_dir = Path(__file__).resolve().parent.parent / "agora_ui"
    if ui_dir.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount(
            "/ui",
            StaticFiles(directory=str(ui_dir), html=True),
            name="ui",
        )

    # Supervisor: relanza solo los modelos locales marcados 'autostart' (p. ej. LAYA) si se caen.
    import threading

    from agora_serve import models as _models

    threading.Thread(target=_models.supervisor_loop, args=(30.0,), daemon=True).start()

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
