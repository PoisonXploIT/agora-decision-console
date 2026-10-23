"""Seguridad de la consola AGORA: politica de red, token de sesion y cabeceras.

Modelo (igual que en CERBERUS): la consola es de un solo usuario y vive en loopback,
pero "solo localhost" no basta (DNS rebinding, otras pestanas, procesos locales).

  1. `Host` debe ser loopback (o `testserver` en tests).
  2. Las rutas que leen o cambian estado (/v1/*, /backends, /models, /catalog, /runs)
     exigen un token de sesion: cookie HttpOnly o cabecera `X-AGORA-Token`.
  3. Los metodos que cambian estado con `Origin` externo se rechazan.
  4. Cabeceras: CSP, nosniff, no-referrer, frame-ancestors none.
  5. Politica de URLs de backend: http solo loopback; https solo allowlist. La clave
     de un backend nunca se envia a un host fuera de la allowlist.

`AGORA_AUTH=off` desactiva el token (solo para la bateria de tests).
"""
from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

COOKIE = "agora_ui"
HEADER = "X-AGORA-Token"
DEFAULT_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}
DEFAULT_API_HOSTS = {"api.typesafe.ai"}
EXEMPT = {"/health"}

CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

_TOKEN: str | None = None


def config_dir() -> Path:
    d = os.environ.get("AGORA_CONFIG_DIR")
    return Path(d) if d else (Path.home() / ".agora")


def allowed_hosts() -> set[str]:
    extra = os.environ.get("AGORA_ALLOWED_HOSTS", "")
    return DEFAULT_HOSTS | {h.strip().lower() for h in extra.split(",") if h.strip()}


def allowed_api_hosts() -> set[str]:
    extra = os.environ.get("AGORA_ALLOWED_API_HOSTS", "")
    return DEFAULT_API_HOSTS | {h.strip().lower() for h in extra.split(",") if h.strip()}


def api_keys() -> set[str]:
    """Claves de servicio para otras herramientas (Authorization: Bearer)."""
    raw = os.environ.get("AGORA_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def auth_enabled() -> bool:
    return os.environ.get("AGORA_AUTH", "on").strip().lower() not in ("off", "0", "false")


def ui_token() -> str:
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    env = os.environ.get("AGORA_UI_TOKEN", "").strip()
    if env:
        _TOKEN = env
        return _TOKEN
    path = config_dir() / "ui_token"
    if path.exists():
        _TOKEN = path.read_text(encoding="utf-8").strip()
    if not _TOKEN:
        _TOKEN = secrets.token_urlsafe(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_TOKEN, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return _TOKEN


def is_loopback(host: str) -> bool:
    h = (host or "").strip("[]").lower()
    if h in ("localhost", "127.0.0.1", "::1"):
        return True
    return h.startswith("127.")


class BadBackendUrl(ValueError):
    """URL de backend no permitida por la politica de red."""


def validate_backend_url(url: str) -> str:
    """Normaliza y valida la URL de un backend.

    - http: solo loopback (LAYAA, Eikos y servidores locales).
    - https: solo hosts de la allowlist (JEV/TypeSafe y los que se anadan por env).
    - sin credenciales en la URL, sin query ni fragmento.
    """
    raw = (url or "").strip()
    if not raw:
        raise BadBackendUrl("URL vacia")
    if any(c in raw for c in ("\n", "\r", "\t", " ")):
        raise BadBackendUrl("la URL contiene espacios o saltos de linea")
    p = urlsplit(raw)
    if not p.scheme or not p.hostname:
        raise BadBackendUrl(f"URL incompleta: {raw!r}")
    if p.username or p.password:
        raise BadBackendUrl("no se permiten credenciales en la URL")
    if p.query or p.fragment:
        raise BadBackendUrl("no se permiten query ni fragmento en la URL base")
    host = p.hostname.lower()
    if p.scheme == "http":
        if not is_loopback(host):
            raise BadBackendUrl(
                f"http solo para loopback; {host!r} requiere https y estar en la allowlist"
            )
        port = p.port or 80
        if not (1024 <= port <= 65535):
            raise BadBackendUrl(f"puerto no permitido: {port}")
    elif p.scheme == "https":
        if not is_loopback(host) and host not in allowed_api_hosts():
            raise BadBackendUrl(
                f"host no permitido: {host!r}. Anadelo a AGORA_ALLOWED_API_HOSTS si es tu proveedor."
            )
    else:
        raise BadBackendUrl(f"esquema no permitido: {p.scheme!r}")
    return raw.rstrip("/")


def _host_ok(host_header: str | None) -> bool:
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host in allowed_hosts()


def _origin_ok(origin: str | None) -> bool:
    if not origin:
        return True
    return _host_ok(urlsplit(origin).netloc or "")


def _presented_token(request: Request) -> str:
    return (request.headers.get(HEADER) or request.cookies.get(COOKIE) or "").strip()


def apikey_allowed(method: str, path: str) -> bool:
    """Que puede hacer una clave de servicio: decidir y leer, nunca administrar."""
    if method == "GET" and path.startswith("/v1/") and path != "/v1/logs":
        return True
    if method == "POST" and path in ("/v1/decide", "/v1/decide/compare",
                                     "/v1/decide/pack", "/v1/questions/from-text"):
        return True
    return bool(method == "POST" and path.startswith("/v1/runs/")
                and path.endswith("/replay"))


def _needs_token(path: str) -> bool:
    if path in EXEMPT or path.startswith("/ui/"):
        return False
    return path.startswith(("/v1/", "/backends", "/models", "/catalog"))


def install(app) -> None:
    token = ui_token()

    @app.middleware("http")
    async def _guard(request: Request, call_next):
        if not _host_ok(request.headers.get("host")):
            return JSONResponse(
                {"detail": "Host no permitido: la consola solo responde en loopback"},
                status_code=403,
            )
        if request.method not in ("GET", "HEAD") and not _origin_ok(request.headers.get("origin")):
            return JSONResponse({"detail": "Origen no permitido"}, status_code=403)
        if auth_enabled() and _needs_token(request.url.path):
            ok_session = hmac.compare_digest(_presented_token(request), token)
            auth = request.headers.get("authorization", "")
            bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            ok_key = bool(bearer) and any(hmac.compare_digest(bearer, k) for k in api_keys())                 and apikey_allowed(request.method, request.url.path)
            if not (ok_session or ok_key):
                return JSONResponse(
                    {"detail": "Falta credencial: cookie de sesion (X-AGORA-Token) o "
                               "Authorization: Bearer <clave de servicio>"},
                    status_code=401,
                )

        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path.startswith("/ui/") and request.method == "GET":
            response.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")
        return response
