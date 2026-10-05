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

Variables de entorno:

- ``AGORA_CHAT_URL``   URL de chat completions (defecto http://127.0.0.1:8099/v1/chat/completions)
- ``AGORA_CHAT_MODEL`` nombre del modelo (si vacio, se toma el primero de /v1/models)
- ``AGORA_CHAT_TIMEOUT`` segundos (defecto 180)
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


def _chat_url() -> str:
    return os.environ.get("AGORA_CHAT_URL", DEFAULT_CHAT_URL)


def _timeout() -> float:
    try:
        return float(os.environ.get("AGORA_CHAT_TIMEOUT", "180"))
    except Exception:
        return 180.0


def _model() -> str:
    model = os.environ.get("AGORA_CHAT_MODEL", "").strip()
    if model:
        return model
    base = _chat_url().replace("/chat/completions", "/models")
    try:
        with urllib.request.urlopen(base, timeout=10) as r:
            data = json.loads(r.read())
        items = data.get("data") or data.get("models") or []
        if items:
            return str(items[0].get("id") or items[0].get("name") or "")
    except Exception:
        pass
    return ""


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
