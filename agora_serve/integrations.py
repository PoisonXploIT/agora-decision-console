"""Integraciones de AGORA: salidas hacia otras herramientas (sinks).

Config local (`~/.agora/integrations.json`, o `AGORA_CONFIG_DIR`):

    {
      "sinks": [
        {"type": "webhook",  "url": "http://127.0.0.1:8790/agora", "events": ["decide"]},
        {"type": "jsonl",    "path": "decisiones.jsonl", "events": ["decide", "compare"]},
        {"type": "syslog",   "host": "127.0.0.1", "port": 5514, "events": ["compare"]},
        {"type": "splunk",   "url": "https://splunk.local:8088/services/collector",
         "token_env": "SPLUNK_HEC_TOKEN", "events": ["decide"]},
        {"type": "telegram", "token_env": "TELEGRAM_BOT_TOKEN", "chat_id": "12345",
         "events": ["decide"]}
      ]
    }

Tambien `AGORA_WEBHOOK_URL` (un webhook para todos los eventos). La clave `webhooks`
del formato antiguo se sigue aceptando y se trata como sinks de tipo webhook.

Politica de red (anti-SSRF): `http` solo loopback; `https` solo hosts de
`AGORA_WEBHOOK_HOSTS`. `jsonl` escribe dentro del directorio de configuracion.
Los envios son asincronos, con timeout de 3 s: nunca bloquean ni rompen una decision.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from agora_serve import logging_setup, metrics, security

EVENTS = {"decide", "compare", "replay", "report"}
TIMEOUT_S = 3.0
TELEGRAM_API = "https://api.telegram.org"
log = logging_setup.get_logger()


def config_dir() -> Path:
    d = os.environ.get("AGORA_CONFIG_DIR")
    return Path(d) if d else (Path.home() / ".agora")


def config_path() -> Path:
    return config_dir() / "integrations.json"


def allowed_hosts() -> set[str]:
    raw = os.environ.get("AGORA_WEBHOOK_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


class BadSink(ValueError):
    """Sink no permitido o mal configurado."""


# Compatibilidad con el nombre anterior (webhooks).
BadWebhook = BadSink


def validate_webhook_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise BadSink("URL vacia")
    p = urlsplit(raw)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise BadSink(f"URL invalida: {raw!r}")
    if p.username or p.password:
        raise BadSink("no se permiten credenciales en la URL")
    host = p.hostname.lower()
    if p.scheme == "http" and not security.is_loopback(host):
        raise BadSink("http solo para loopback; usa https y AGORA_WEBHOOK_HOSTS")
    if p.scheme == "https" and host not in allowed_hosts():
        raise BadSink(f"host de webhook no permitido: {host!r}")
    return raw


def _validate_jsonl(it: dict) -> dict:
    raw = str(it.get("path") or "").strip()
    if not raw:
        raise BadSink("jsonl sin 'path'")
    base = config_dir().resolve()
    path = (base / raw).resolve()
    if base not in path.parents:
        raise BadSink("jsonl debe escribir dentro del directorio de configuracion")
    if path.suffix.lower() not in (".jsonl", ".log"):
        raise BadSink("jsonl debe usar extension .jsonl o .log")
    return {"path": str(path)}


def _validate_syslog(it: dict) -> dict:
    host = str(it.get("host") or "").strip().lower()
    try:
        port = int(it.get("port") or 514)
    except (TypeError, ValueError) as e:
        raise BadSink("puerto syslog invalido") from e
    if not host or not (1 <= port <= 65535):
        raise BadSink("syslog necesita host y puerto validos")
    extra = {h.strip().lower() for h in os.environ.get("AGORA_SYSLOG_HOSTS", "").split(",") if h.strip()}
    if not security.is_loopback(host) and host not in extra:
        raise BadSink(f"host syslog no permitido: {host!r}")
    return {"host": host, "port": port}


def _validate_telegram(it: dict) -> dict:
    token_env = str(it.get("token_env") or "TELEGRAM_BOT_TOKEN").strip()
    chat = str(it.get("chat_id") or "").strip()
    if not chat.lstrip("-").isdigit():
        raise BadSink("telegram necesita chat_id numerico")
    return {"token_env": token_env, "chat_id": chat}


def _validate_splunk(it: dict) -> dict:
    url = validate_webhook_url(str(it.get("url") or ""))
    token_env = str(it.get("token_env") or "SPLUNK_HEC_TOKEN").strip()
    return {"url": url, "token_env": token_env}


def _validate_sink(it: dict) -> dict | None:
    if not isinstance(it, dict):
        return None
    kind = str(it.get("type") or ("webhook" if it.get("url") else "")).strip().lower()
    events = [e for e in (it.get("events") or sorted(EVENTS)) if e in EVENTS]
    base = {"type": kind, "events": events or sorted(EVENTS),
            "enabled": bool(it.get("enabled", True)), "source": it.get("source", "config")}
    try:
        if kind == "webhook":
            return {**base, **_validate_webhook_url_short(it)}
        if kind == "jsonl":
            return {**base, **_validate_jsonl(it)}
        if kind == "syslog":
            return {**base, **_validate_syslog(it)}
        if kind == "telegram":
            return {**base, **_validate_telegram(it)}
        if kind == "splunk":
            return {**base, **_validate_splunk(it)}
        raise BadSink(f"tipo desconocido: {kind!r}")
    except BadSink as e:
        log.warning("sink descartado (%s): %s", it.get("url") or it.get("path") or kind, e)
        return None


def _validate_webhook_url_short(it: dict) -> dict:
    return {"url": validate_webhook_url(str(it.get("url") or ""))}


def load_sinks() -> list[dict]:
    items: list[dict] = []
    env = os.environ.get("AGORA_WEBHOOK_URL", "").strip()
    if env:
        items.append({"type": "webhook", "url": env, "events": sorted(EVENTS),
                      "enabled": True, "source": "env"})
    p = config_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("integrations.json ilegible")
            data = {}
        if isinstance(data, dict):
            for it in data.get("sinks", []) or []:
                items.append({**it, "source": "config"} if isinstance(it, dict) else it)
            for it in data.get("webhooks", []) or []:  # formato antiguo
                if isinstance(it, dict):
                    items.append({**it, "type": "webhook", "source": "config"})
    out = []
    for it in items:
        sink = _validate_sink(it)
        if sink:
            out.append(sink)
    return out


def status() -> list[dict]:
    """Version saneada para la UI: sin tokens ni rutas absolutas."""
    out = []
    for s in load_sinks():
        row = {"type": s["type"], "events": s["events"], "enabled": s["enabled"],
               "source": s.get("source")}
        if s["type"] in ("webhook", "splunk"):
            p = urlsplit(s["url"])
            row.update({"host": p.hostname, "path": p.path or "/"})
        elif s["type"] == "jsonl":
            row["file"] = Path(s["path"]).name
        elif s["type"] == "syslog":
            row.update({"host": s["host"], "port": s["port"]})
        elif s["type"] == "telegram":
            row["chat"] = s["chat_id"][:3] + "***"
        out.append(row)
    return out


def _post_json(url: str, payload: dict, headers: dict | None = None) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "agora-sink/1")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            log.info("sink %s -> %s", urlsplit(url).hostname, r.status)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        metrics.webhook_failure()
        log.warning("sink %s fallo: %s", urlsplit(url).hostname, e)


def _deliver(sink: dict, body: dict) -> None:
    kind = sink["type"]
    if kind == "webhook":
        _post_json(sink["url"], body)
    elif kind == "splunk":
        token = os.environ.get(sink["token_env"], "")
        if not token:
            metrics.webhook_failure()
            log.warning("splunk sin %s", sink["token_env"])
            return
        _post_json(sink["url"], {"event": body, "source": "agora"},
                   {"Authorization": "Splunk " + token})
    elif kind == "jsonl":
        try:
            path = Path(sink["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(body, ensure_ascii=False) + "\n")
            try:
                path.chmod(0o600)
            except OSError:
                pass
        except OSError as e:
            metrics.webhook_failure()
            log.warning("jsonl fallo: %s", e)
    elif kind == "syslog":
        try:
            payload = json.dumps(body, ensure_ascii=False)
            msg = f"<14>1 - agora - - - {payload}"
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(msg.encode("utf-8")[:60000], (sink["host"], sink["port"]))
        except OSError as e:
            metrics.webhook_failure()
            log.warning("syslog fallo: %s", e)
    elif kind == "telegram":
        token = os.environ.get(sink["token_env"], "")
        if not token:
            metrics.webhook_failure()
            log.warning("telegram sin %s", sink["token_env"])
            return
        text = json.dumps(body, ensure_ascii=False)[:3800]
        data = urllib.parse.urlencode({"chat_id": sink["chat_id"], "text": text}).encode()
        req = urllib.request.Request(f"{TELEGRAM_API}/bot{token}/sendMessage", data=data,
                                     method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S):
                log.info("sink telegram ok")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            metrics.webhook_failure()
            log.warning("telegram fallo: %s", e)


def emit(event: str, payload: dict) -> None:
    """Lanza los sinks suscritos sin bloquear la peticion."""
    if event not in EVENTS:
        return
    body = {"event": event, "ts": time.time(), "source": "agora", **payload}
    for sink in load_sinks():
        if sink["enabled"] and event in sink["events"]:
            threading.Thread(target=_deliver, args=(sink, body), daemon=True).start()
