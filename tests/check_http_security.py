"""Comprobaciones HTTP de seguridad contra la consola en marcha.

Uso (con AGORA levantada en 127.0.0.1:8800):

    .venv\\Scripts\\python.exe tests\\check_http_security.py

No manda trafico a Internet: todo va a loopback; las URLs "malas" solo aparecen en
el cuerpo JSON para verificar que el servidor las rechaza antes de usarlas.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8800"
HOME = Path(os.environ.get("AGORA_CONFIG_DIR") or (Path.home() / ".agora"))
TOKEN_FILE = HOME / "ui_token"
fallos = 0


def call(path: str, method: str = "GET", body=None, token: bool = True,
         host: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if token and TOKEN_FILE.exists():
        req.add_header("X-AGORA-Token", TOKEN_FILE.read_text(encoding="utf-8").strip())
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def check(name: str, got, want) -> None:
    global fallos
    ok = got == want if not isinstance(want, (list, tuple)) else got in want
    print(f"{'OK  ' if ok else 'FAIL'} {name}: {got} (esperado {want})")
    if not ok:
        fallos += 1


def main() -> int:
    st, headers, _ = call("/ui/", token=False)
    check("GET /ui/ publico", st, 200)
    check("CSP", "script-src 'self'" in (headers.get("content-security-policy") or ""), True)
    check("nosniff", headers.get("x-content-type-options"), "nosniff")
    check("cookie de sesion", "agora_ui=" in (headers.get("set-cookie") or ""), True)

    check("API sin token", call("/v1/packs", token=False)[0], 401)
    check("API con token", call("/v1/packs")[0], 200)
    check("health publico", call("/health", token=False)[0], 200)
    check("Host no local", call("/health", token=False, host="rebind.example")[0], 403)

    check("backend http remoto",
          call("/backends", "POST", {"name": "malo", "kind": "http",
                                     "base_url": "http://198.18.0.1:8787"})[0], 422)
    check("backend https fuera de allowlist",
          call("/backends", "POST", {"name": "malo2", "kind": "http",
                                     "base_url": "https://agora.invalid"})[0], 422)
    check("backend nombre invalido",
          call("/backends", "POST", {"name": "../x", "kind": "http",
                                     "base_url": "http://127.0.0.1:8787"})[0], 422)

    check("stop sin confirmar",
          call("/models/laya/stop", "POST", {})[0], 428)
    check("state enorme",
          call("/v1/decide", "POST", {
              "backend": "mock",
              "question": {"id": "q", "type": "choice", "prompt": "p", "criteria": ["a", "b"]},
              "state": {"x": "a" * 70000},
          })[0], 413)

    print("\nRESULTADO:", "OK" if fallos == 0 else f"{fallos} fallos")
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
