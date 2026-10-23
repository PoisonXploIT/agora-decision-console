"""Tests de los sinks de integracion (jsonl, syslog, telegram, splunk)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from agora_serve import integrations as ig


def test_jsonl_dentro_de_config():
    sink = ig._validate_sink({"type": "jsonl", "path": "decisiones.jsonl"})
    assert sink and sink["path"].endswith("decisiones.jsonl")


def test_jsonl_fuera_rechazado():
    assert ig._validate_sink({"type": "jsonl", "path": "../../fuera.jsonl"}) is None


def test_syslog_loopback_ok():
    sink = ig._validate_sink({"type": "syslog", "host": "127.0.0.1", "port": 5514})
    assert sink and sink["port"] == 5514


def test_syslog_externo_rechazado():
    assert ig._validate_sink({"type": "syslog", "host": "10.9.9.9", "port": 514}) is None


def test_telegram_chat_invalido():
    assert ig._validate_sink({"type": "telegram", "chat_id": "abc"}) is None
    assert ig._validate_sink({"type": "telegram", "chat_id": "-100123"}) is not None


def test_splunk_fuera_de_allowlist():
    assert ig._validate_sink({"type": "splunk", "url": "https://10.9.9.9/x"}) is None


def test_emit_escribe_jsonl():
    cfg = Path(os.environ["AGORA_CONFIG_DIR"])
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "integrations.json").write_text(json.dumps({
        "sinks": [{"type": "jsonl", "path": "eventos.jsonl", "events": ["decide"]}]
    }), encoding="utf-8")
    ig.emit("decide", {"backend": "mock", "question_id": "q1"})
    target = cfg / "eventos.jsonl"
    for _ in range(60):
        if target.exists() and target.read_text(encoding="utf-8").strip():
            break
        time.sleep(0.05)
    line = json.loads(target.read_text(encoding="utf-8").splitlines()[-1])
    assert line["event"] == "decide" and line["question_id"] == "q1"
