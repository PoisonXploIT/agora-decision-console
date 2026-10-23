"""Cliente HTTP de AGORA reutilizable por el servidor MCP y las integraciones."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_URL = os.environ.get("AGORA_URL", "http://127.0.0.1:8800")


class AgoraError(RuntimeError):
    pass


def config_dir() -> Path:
    d = os.environ.get("AGORA_CONFIG_DIR")
    return Path(d) if d else (Path.home() / ".agora")


def session_token() -> str:
    """Token de la sesion local, para clientes que corren en el mismo equipo."""
    p = config_dir() / "ui_token"
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


class AgoraClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 token: str | None = None, timeout: float = 90.0):
        self.base = (base_url or DEFAULT_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("AGORA_API_KEY", "")
        self.token = token if token is not None else ("" if self.api_key else session_token())
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        h = {"User-Agent": "agora-client/1"}
        if self.api_key:
            h["Authorization"] = "Bearer " + self.api_key
        elif self.token:
            h["X-AGORA-Token"] = self.token
        return h

    def call(self, path: str, method: str = "GET", body: dict | None = None) -> Any:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        for k, v in self._headers().items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            raise AgoraError(f"HTTP {e.code} en {path}: {detail}") from e
        except urllib.error.URLError as e:
            raise AgoraError(f"sin conexion con {self.base}: {e}") from e

    # --- atajos -----------------------------------------------------------
    def health(self) -> dict:
        return self.call("/health")

    def packs(self) -> list[dict]:
        return self.call("/v1/packs").get("packs", [])

    def decide(self, question: dict, state: Any, backend: str = "mock") -> dict:
        return self.call("/v1/decide", "POST",
                         {"question": question, "state": state, "backend": backend})

    def decide_pack(self, pack: str, state: Any,
                    backends: list[str] | None = None) -> dict:
        body: dict = {"pack": pack, "state": state}
        if backends:
            body["backends"] = backends
        return self.call("/v1/decide/pack", "POST", body)

    def compare(self, question: dict, state: Any,
                backends: list[str] | None = None) -> dict:
        body: dict = {"question": question, "state": state}
        if backends:
            body["backends"] = backends
        return self.call("/v1/decide/compare", "POST", body)

    def history(self, limit: int = 20, backend: str | None = None) -> dict:
        q = f"?limit={int(limit)}" + (f"&backend={backend}" if backend else "")
        return self.call("/v1/runs" + q)
