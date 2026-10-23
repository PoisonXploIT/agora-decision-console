"""Cliente minimo de AGORA para otras herramientas (solo stdlib).

Uso:
    export AGORA_URL=http://127.0.0.1:8800
    export AGORA_API_KEY=clave-para-sec-dashboard
    python integrations/agora_client.py
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_URL = os.environ.get("AGORA_URL", "http://127.0.0.1:8800")
DEFAULT_KEY = os.environ.get("AGORA_API_KEY", "")


class AgoraError(RuntimeError):
    pass


class AgoraClient:
    def __init__(self, base_url: str = DEFAULT_URL, api_key: str = DEFAULT_KEY,
                 timeout: float = 60.0):
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _call(self, path: str, method: str = "GET", body: dict | None = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", "Bearer " + self.api_key)
        req.add_header("User-Agent", "agora-client/1")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise AgoraError(f"HTTP {e.code} en {path}: {detail}") from e
        except urllib.error.URLError as e:
            raise AgoraError(f"sin conexion con {self.base}: {e}") from e

    def packs(self) -> list[dict]:
        return self._call("/v1/packs").get("packs", [])

    def decide(self, question: dict, state: Any, backend: str = "mock") -> dict:
        return self._call("/v1/decide", "POST",
                          {"question": question, "state": state, "backend": backend})

    def decide_pack(self, pack: str, state: Any, backends: list[str] | None = None) -> dict:
        body: dict = {"pack": pack, "state": state}
        if backends:
            body["backends"] = backends
        return self._call("/v1/decide/pack", "POST", body)

    def history(self, limit: int = 20, backend: str | None = None) -> dict:
        q = f"?limit={limit}" + (f"&backend={backend}" if backend else "")
        return self._call("/v1/runs" + q)


def _demo() -> int:
    cli = AgoraClient()
    packs = cli.packs()
    print(f"packs: {[p['name'] for p in packs]}")
    if not packs:
        return 1
    pack = packs[0]["name"]
    out = cli.decide_pack(pack, {"demo": True}, ["mock"])
    for row in out["results"]:
        pb = row["by_backend"].get("mock", {})
        print(row["question_id"], "->", pb.get("probabilities"))
    print("historial:", cli.history(3)["count"], "runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(_demo())
