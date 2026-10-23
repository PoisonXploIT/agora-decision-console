"""Servidor MCP de AGORA sobre stdio (JSON-RPC 2.0).

Uso:
    python -m agora_mcp            (o `agora mcp`)

Configuracion tipica en un cliente MCP (Claude Desktop, Cursor, etc.):

    {
      "mcpServers": {
        "agora": {
          "command": "C:/Users/Sammi/AI/agora/.venv/Scripts/python.exe",
          "args": ["-m", "agora_mcp"],
          "env": {"AGORA_URL": "http://127.0.0.1:8800", "AGORA_API_KEY": "..."}
        }
      }
    }

Autenticacion: `AGORA_API_KEY` (clave de servicio) o, si el cliente corre en el
mismo equipo, el token de sesion de `~/.agora/ui_token`. Todo va por loopback.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from .client import AgoraClient
from .tools import TOOLS, dispatch

PROTOCOL = "2024-11-05"
SERVER_INFO = {"name": "agora", "version": "0.1.0"}


class Server:
    def __init__(self, client: AgoraClient | None = None):
        self.client = client or AgoraClient()

    def handle(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        """Procesa un mensaje JSON-RPC y devuelve la respuesta (o None si es notificacion)."""
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            return self._ok(mid, {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            })
        if method in ("notifications/initialized", "initialized"):
            return None
        if method == "ping":
            return self._ok(mid, {})
        if method == "tools/list":
            return self._ok(mid, {"tools": TOOLS})
        if method == "resources/list":
            return self._ok(mid, {"resources": []})
        if method == "prompts/list":
            return self._ok(mid, {"prompts": []})
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                return self._err(mid, -32602, "arguments debe ser un objeto")
            result = dispatch(self.client, str(name), args)
            return self._ok(mid, result)
        if method == "shutdown":
            return self._ok(mid, {})
        return self._err(mid, -32601, f"metodo no soportado: {method}")

    @staticmethod
    def _ok(mid: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    @staticmethod
    def _err(mid: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def main() -> int:
    server = Server()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            print(json.dumps(Server._err(None, -32700, "JSON invalido")), flush=True)
            continue
        if not isinstance(msg, dict):
            print(json.dumps(Server._err(None, -32600, "mensaje invalido")), flush=True)
            continue
        resp = server.handle(msg)
        if resp is not None:
            print(json.dumps(resp, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
