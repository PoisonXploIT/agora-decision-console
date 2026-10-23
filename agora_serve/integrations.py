"""Integraciones de AGORA: webhooks de salida hacia otras herramientas.

Config local (`~/.agora/integrations.json`, o `AGORA_CONFIG_DIR`):

    {
      "webhooks": [
        {"url": "http://127.0.0.1:8790/agora", "events": ["decide"], "enabled": true}
      ]
    }

Tambien `AGORA_WEBHOOK_URL` (un unico webhook para todos los eventos).

Politica de red (anti-SSRF): `http` solo loopback; `https` solo hosts de
`AGORA_WEBHOOK_HOSTS`. El envio es asincrono, con timeout de 3 s y sin bloquear la
decision. Los fallos se registran en el log, nunca devuelven error al usuario.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from agora_serve import logging_setup, security

EVENTS = {"decide", "compare", "replay", "report"}
TIMEOUT_S = 3.0
log = logging_setup.get_logger()


def config_dir() -> Path:
    d = os.environ.get("AGORA_CONFIG_DIR")
    return Path(d) if d else (Path.home() / ".agora")


def config_path() -> Path:
    return config_dir() / "integrations.json"


def allowed_hosts() -> set[str]:
    raw = os.environ.get("AGORA_WEBHOOK_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


class BadWebhook(ValueError):
    """URL de webhook no permitida."""


def validate_webhook_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise BadWebhook("URL vacia")
    p = urlsplit(raw)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise BadWebhook(f"URL invalida: {raw!r}")
    if p.username or p.password:
        raise BadWebhook("no se permiten credenciales en la URL")
    host = p.hostname.lower()
    if p.scheme == "http" and not security.is_loopback(host):
        raise BadWebhook("http solo para loopback; usa https y AGORA_WEBHOOK_HOSTS")
    if p.scheme == "https" and host not in allowed_hosts():
        raise BadWebhook(f"host de webhook no permitido: {host!r}")
    return raw


def load() -> list[dict]:
    items: list[dict] = []
    env = os.environ.get("AGORA_WEBHOOK_URL", "").strip()
    if env:
        items.append({"url": env, "events": sorted(EVENTS), "enabled": True, "source": "env"})
    p = config_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for it in data.get("webhooks", []) if isinstance(data, dict) else []:
                if isinstance(it, dict) and it.get("url"):
                    items.append({**it, "source": "config"})
        except (OSError, ValueError):
            log.warning("integrations.json ilegible")
    out = []
    for it in items:
        try:
            url = validate_webhook_url(str(it["url"]))
        except BadWebhook as e:
            log.warning("webhook descartado (%s): %s", it.get("url"), e)
            continue
        events = [e for e in (it.get("events") or sorted(EVENTS)) if e in EVENTS]
        out.append({"url": url, "events": events or sorted(EVENTS),
                    "enabled": bool(it.get("enabled", True)), "source": it.get("source")})
    return out


def status() -> list[dict]:
    """Version saneada para la UI: sin query ni credenciales."""
    out = []
    for it in load():
        p = urlsplit(it["url"])
        out.append({"host": p.hostname, "path": p.path or "/", "events": it["events"],
                    "enabled": it["enabled"], "source": it["source"]})
    return out


def _post(url: str, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "agora-webhook/1")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            log.info("webhook %s -> %s", url, r.status)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log.warning("webhook %s fallo: %s", url, e)


def emit(event: str, payload: dict) -> None:
    """Lanza los webhooks suscritos sin bloquear la peticion."""
    if event not in EVENTS:
        return
    for it in load():
        if not it["enabled"] or event not in it["events"]:
            continue
        body = {"event": event, "ts": time.time(), "source": "agora", **payload}
        threading.Thread(target=_post, args=(it["url"], body), daemon=True).start()
