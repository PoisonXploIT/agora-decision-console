r"""chat_config.py - configuracion del LLM de chat (el traductor de lenguaje natural).

AGORA separa dos papeles:

- **backend de decision**: LAYA / Eikos / JEV / mock / un chat local. Responde una
  pregunta ya tipada con una distribucion sobre los criterios.
- **LLM de chat (traductor)**: convierte una frase en lenguaje natural en una
  `Question` tipada (id, type, prompt, criteria) y, si hace falta, elige quien
  responde. Ese modelo NO decide: compila la pregunta.

Se persiste en el perfil del usuario (nunca en el repo):

    %USERPROFILE%\\.agora\\chat.json

    {"base_url": "http://127.0.0.1:8080", "model": "qwen3.8-flash-next-q2_0",
     "timeout": 180}

Prioridad: fichero > variables de entorno (AGORA_CHAT_URL / AGORA_CHAT_MODEL) >
defecto :8099. Cualquier LLM local compatible con OpenAI vale: llama.cpp, Ollama,
LM Studio, Strata, vLLM.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agora_adapters.chat import completions_url, models_url

DEFAULT_BASE = "http://127.0.0.1:8099"
DEFAULT_TIMEOUT = 180.0


def _dir() -> Path:
    d = os.environ.get("AGORA_CONFIG_DIR")
    return Path(d) if d else (Path.home() / ".agora")


def config_path() -> Path:
    return _dir() / "chat.json"


def load() -> dict[str, Any]:
    """Config vigente, con las env como capa de respaldo."""
    cfg: dict[str, Any] = {}
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cfg = data
    except Exception:  # noqa: BLE001
        pass
    base = (cfg.get("base_url") or os.environ.get("AGORA_CHAT_URL") or DEFAULT_BASE).strip()
    # admiten la URL completa de completions: la normalizamos a base
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    if base.endswith("/v1"):
        base = base[:-3]
    try:
        timeout = float(cfg.get("timeout") or os.environ.get("AGORA_CHAT_TIMEOUT") or DEFAULT_TIMEOUT)
    except Exception:  # noqa: BLE001
        timeout = DEFAULT_TIMEOUT
    return {
        "base_url": base.rstrip("/"),
        "model": (cfg.get("model") or os.environ.get("AGORA_CHAT_MODEL") or "").strip(),
        "timeout": timeout,
        "url": completions_url(base),
    }


def save(base_url: str, model: str | None = None, timeout: float | None = None) -> dict[str, Any]:
    base = (base_url or "").strip()
    if not base:
        raise ValueError("base_url requerida")
    if not base.startswith(("http://", "https://")):
        raise ValueError("base_url debe empezar por http:// o https://")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    if base.endswith("/v1"):
        base = base[:-3]
    cfg = {
        "base_url": base.rstrip("/"),
        "model": (model or "").strip(),
        "timeout": float(timeout) if timeout else DEFAULT_TIMEOUT,
    }
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(p)
    return {**cfg, "url": completions_url(cfg["base_url"])}


def list_models(base_url: str | None = None, timeout: float = 8.0) -> list[str]:
    """Modelos que expone ese servidor (descubrimiento para la UI)."""
    url = models_url(base_url or load()["base_url"])
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read())
    except Exception:  # noqa: BLE001
        return []
    items = data.get("data") or data.get("models") or []
    out = []
    for it in items:
        name = str(it.get("id") or it.get("name") or "").strip()
        if name:
            out.append(name)
    return out


def probe(base_url: str | None = None, timeout: float = 4.0) -> bool:
    """Hay servidor de chat respondiendo en esa base_url."""
    try:
        with urllib.request.urlopen(models_url(base_url or load()["base_url"]), timeout=timeout) as r:
            return 200 <= getattr(r, "status", 200) < 500
    except Exception:  # noqa: BLE001
        return False


def scan() -> list[dict[str, Any]]:
    """Puertos habituales de LLM local que estan vivos (ayuda para la UI)."""
    candidatos = [
        ("llama.cpp", "http://127.0.0.1:8080"),
        ("llama.cpp 8099", "http://127.0.0.1:8099"),
        ("Ollama", "http://127.0.0.1:11434"),
        ("LM Studio", "http://127.0.0.1:1234"),
        ("vLLM", "http://127.0.0.1:8000"),
        ("LAYA", "http://127.0.0.1:8787"),
        ("Eikos", "http://127.0.0.1:8901"),
    ]
    vivos = []
    for label, base in candidatos:
        if probe(base):
            vivos.append({"label": label, "base_url": base, "models": list_models(base)})
    return vivos


__all__ = ["load", "save", "list_models", "probe", "scan", "config_path", "DEFAULT_BASE"]
