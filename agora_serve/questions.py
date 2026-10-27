"""questions.py - convierte una instruccion en lenguaje natural en una pregunta tipada.

Usa el modelo de chat LOCAL (OpenAI-compatible, por defecto el de :8099) para
traducir una frase como "clasifica un comando bash en seguro, dudoso o
peligroso" al JSON de una ``Question`` de AGORA:

    {"id": "...", "type": "choice"|"score"|"noul", "prompt": "...", "criteria": [...]}

Reglas:

- El resultado se VALIDA con el esquema ``Question`` (si no cumple, 422).
- Nada de nube obligatoria: apunta a un endpoint local por defecto.
- El texto del usuario es dato, no instruccion para el modelo que genera
  (el system prompt manda).

De donde sale el LLM de chat (por prioridad):

1. ``~\.agora\chat.json`` configurado desde la UI (``agora_serve.chat_config``)
2. ``AGORA_CHAT_URL`` / ``AGORA_CHAT_MODEL`` / ``AGORA_CHAT_TIMEOUT``
3. defecto http://127.0.0.1:8099
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from pydantic import ValidationError

from agora_core.schemas import Question
from agora_serve import chat_config

DEFAULT_CHAT_URL = "http://127.0.0.1:8099/v1/chat/completions"

_SYSTEM = (
    "Conviertes instrucciones en espanol a UNA pregunta tipada de decision. "
    "Devuelve SOLO un objeto JSON valido, sin texto alrededor ni bloques de codigo, con estas claves: "
    'id (string corto en minusculas, sin espacios), '
    'type (uno de "choice", "score", "noul"), '
    "prompt (la pregunta, string), "
    "criteria (array de strings con las opciones o niveles, en orden, sin repetir; "
    'si type es "score" son niveles de menor a mayor y hacen falta al menos dos). '
    "No anadas explicaciones ni claves extra."
)


class ChatError(RuntimeError):
    """No se pudo obtener una pregunta valida del modelo de chat."""


def _cfg() -> dict:
    return chat_config.load()


def _chat_url() -> str:
    return _cfg()["url"]


def _timeout() -> float:
    return _cfg()["timeout"]


def _model() -> str:
    cfg = _cfg()
    if cfg["model"]:
        return cfg["model"]
    models = chat_config.list_models(cfg["base_url"])
    return models[0] if models else ""


def chat_info() -> dict:
    """Quien genera el JSON: el LLM de chat, no el modelo de decision."""
    cfg = _cfg()
    return {
        "tipo": "LLM de chat (instruct)",
        "url": cfg["url"],
        "model": _model(),
        "vivo": chat_config.probe(cfg["base_url"]),
    }


def _extract_json(text: str) -> dict[str, Any]:
    """Saca el primer objeto JSON del texto (tolera vallas ``` y prosa)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    start = t.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(t)):
            if t[i] == "{":
                depth += 1
            elif t[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(t[start : i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
                    break
        start = t.find("{", start + 1)
    raise ChatError(f"el modelo no devolvio JSON: {text[:200]!r}")


def _post_chat(messages: list[dict], model: str) -> str:
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 700,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        _chat_url(),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_timeout()) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise ChatError(f"chat HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ChatError(f"no se pudo hablar con el chat local ({_chat_url()}): {e}") from e
    try:
        return str(data["choices"][0]["message"]["content"] or "")
    except Exception as e:  # noqa: BLE001
        raise ChatError(f"respuesta de chat inesperada: {str(data)[:200]}") from e


def from_text(text: str, *, default_type: str = "choice") -> Question:
    """Traduce una instruccion a una ``Question`` validada.

    Reintenta una vez con el error de validacion por si el modelo se colo.
    """
    text = (text or "").strip()
    if not text:
        raise ChatError("instruccion vacia")
    model = _model()
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Instruccion: {text}\nTipo preferido: {default_type}"},
    ]
    last_err: Exception | None = None
    for _ in range(2):
        content = _post_chat(messages, model)
        try:
            obj = _extract_json(content)
            return Question.model_validate(obj)
        except ValidationError as e:
            last_err = e
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": "El JSON no cumple el esquema: "
                    + "; ".join(f"{x['loc'][-1]}: {x['msg']}" for x in e.errors())
                    + ". Devuelve SOLO el JSON corregido.",
                }
            )
        except ChatError as e:
            last_err = e
    raise ChatError(f"no se pudo obtener una pregunta valida: {last_err}")


_COMPILO_SYSTEM = (
    _SYSTEM
    + " Si ademas te dan una lista de backends de decision disponibles, anade la clave "
    '"backend" con el nombre del backend que debe responder (el que mejor encaje con el '
    'tipo de pregunta y con su privacidad: local antes que cloud) y la clave "motivo" '
    "con una frase breve de por que ese y no otro."
)


def compile_question(
    text: str,
    *,
    default_type: str = "choice",
    backends: list[dict] | None = None,
) -> tuple[Question, dict]:
    """Traduce lenguaje natural a (Question tipada, routing).

    El LLM de chat NO decide: compila la pregunta y sugiere quien la responde.
    La validacion final del routing la hace el codigo (el backend sugerido tiene
    que existir y soportar el tipo de pregunta).
    """
    text = (text or "").strip()
    if not text:
        raise ChatError("instruccion vacia")
    backends = backends or []
    lista = ", ".join(
        f"{b['name']} (tipo={b.get('kind','?')}, privacidad={b.get('privacy','local')}, "
        f"soporta={','.join(b.get('supports') or [])})"
        for b in backends
    ) or "ninguno"
    model = _model()
    messages = [
        {"role": "system", "content": _COMPILO_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Instruccion: {text}\nTipo preferido: {default_type}\n"
                f"Backends de decision disponibles: {lista}"
            ),
        },
    ]
    last_err: Exception | None = None
    for _ in range(2):
        content = _post_chat(messages, model)
        try:
            obj = _extract_json(content)
            q = Question.model_validate(obj)
            sugerido = str(obj.get("backend") or "").strip().lower()
            motivo = str(obj.get("motivo") or "").strip()
            validos = {b["name"] for b in backends}
            soporta = {
                b["name"]: set(b.get("supports") or []) for b in backends
            }
            if sugerido in validos and q.type.value in soporta[sugerido]:
                routing = {"backend": sugerido, "motivo": motivo or "sugerido por el LLM",
                           "fuente": "llm"}
            else:
                routing = {"backend": None, "motivo": "el LLM no dio un backend valido",
                           "fuente": "llm"}
            return q, routing
        except ValidationError as e:
            last_err = e
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": "El JSON no cumple el esquema: "
                + "; ".join(f"{x['loc'][-1]}: {x['msg']}" for x in e.errors())
                + ". Devuelve SOLO el JSON corregido.",
            })
        except ChatError as e:
            last_err = e
    raise ChatError(f"no se pudo compilar la pregunta: {last_err}")


_STATE_SYSTEM = (
    "Extraes los DATOS de una descripcion en lenguaje natural y devuelves SOLO un "
    "objeto JSON valido, sin texto alrededor. Claves en snake_case ASCII; valores "
    "string, numero, booleano, array u objeto. No conviertas el texto en una "
    "instruccion ni anadas claves como 'instruction', 'debe' o 'hay_que'. Si el "
    "texto menciona un comando, una URL, un puerto o un usuario, ponlos como campos "
    "concretos (comando, url, puerto, usuario). Maximo 30 claves."
)


def state_from_text(text: str) -> dict:
    """Convierte una descripcion en lenguaje natural en el `state` de AGORA.

    El resultado es DATO: se valida que sea un objeto JSON y se limita su tamano.
    """
    text = (text or "").strip()
    if not text:
        raise ChatError("descripcion vacia")
    model = _model()
    messages = [
        {"role": "system", "content": _STATE_SYSTEM},
        {"role": "user", "content": text},
    ]
    last_err: Exception | None = None
    for _ in range(2):
        content = _post_chat(messages, model)
        try:
            obj = _extract_json(content)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
        if not isinstance(obj, dict):
            last_err = ChatError("el estado generado no es un objeto JSON")
            continue
        if len(obj) > 30:
            obj = {k: v for k, v in list(obj.items())[:30]}
        return obj
    raise ChatError(f"no se pudo generar el estado: {last_err}")
