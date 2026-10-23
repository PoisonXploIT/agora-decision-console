"""Tests del servidor MCP (sin red: cliente falso)."""
from __future__ import annotations

import json

from agora_mcp.server import Server


class FakeClient:
    def packs(self):
        return [{"name": "injection.precheck", "title": "Pre-check", "part": "SOC",
                 "questions": [{"id": "q1"}, {"id": "q2"}]}]

    def decide_pack(self, pack, state, backends=None):
        return {"pack": pack, "backends": backends or ["mock"],
                "results": [{"question_id": "q1", "prompt": "p", "type": "choice",
                             "by_backend": {"mock": {"probabilities": {"a": 0.9, "b": 0.1},
                                                     "latency_ms": 3}}}],
                "errors": {}}

    def compare(self, question, state, backends=None):
        return {"question_id": question.get("id"), "agreement": {"winner": "a"},
                "results": {}, "errors": {}}

    def history(self, limit=20, backend=None):
        return {"count": 7, "runs": [{"id": "r1"}]}

    def health(self):
        return {"ok": True, "service": "agora", "backends": ["mock"]}


def _call(server, method, params=None, mid=1):
    return server.handle({"jsonrpc": "2.0", "id": mid, "method": method,
                          "params": params or {}})


def test_initialize():
    srv = Server(FakeClient())
    r = _call(srv, "initialize")
    assert r["result"]["protocolVersion"]
    assert r["result"]["capabilities"]["tools"] is not None


def test_tools_list():
    srv = Server(FakeClient())
    tools = _call(srv, "tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"agora_packs", "agora_decide", "agora_compare",
            "agora_history", "agora_health"} == names
    for t in tools:
        assert t["description"] and t["inputSchema"]["type"] == "object"


def test_tool_packs():
    srv = Server(FakeClient())
    r = _call(srv, "tools/call", {"name": "agora_packs", "arguments": {}})
    data = json.loads(r["result"]["content"][0]["text"])
    assert data[0]["name"] == "injection.precheck"
    assert data[0]["questions"] == 2


def test_tool_decide_resume():
    srv = Server(FakeClient())
    r = _call(srv, "tools/call", {"name": "agora_decide",
                                  "arguments": {"pack": "injection.precheck", "state": {}}})
    data = json.loads(r["result"]["content"][0]["text"])
    assert data["pack"] == "injection.precheck"
    assert data["results"][0]["backends"]["mock"]["verdict"] == "a"


def test_tool_desconocida():
    srv = Server(FakeClient())
    r = _call(srv, "tools/call", {"name": "no-existe", "arguments": {}})
    assert r["result"]["isError"] is True


def test_metodo_desconocido():
    srv = Server(FakeClient())
    r = _call(srv, "no/metodo")
    assert r["error"]["code"] == -32601


def test_notificacion_sin_respuesta():
    srv = Server(FakeClient())
    assert srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
