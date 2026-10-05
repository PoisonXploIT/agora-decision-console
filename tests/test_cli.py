"""Tests de la CLI de AGORA invocando main() (F4)."""
from __future__ import annotations

import contextlib
import io
import json

from agora.cli import main


def _run(*argv: str) -> tuple[int, dict | list]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(list(argv))
    out = buf.getvalue().strip()
    return int(code), (json.loads(out) if out else None)


def test_cli_backends():
    code, body = _run("backends")
    assert code == 0
    names = [b["name"] for b in body["backends"]]
    assert "mock" in names and "laya" in names


def test_cli_decide_choice_orden_canonico():
    code, body = _run(
        "decide", "--question", "p", "--criteria", "zeta", "alpha", "mida"
    )
    assert code == 0
    assert list(body["probabilities"]) == ["zeta", "alpha", "mida"]
    assert sum(body["probabilities"].values()) == 1.0
    assert body["trace"]["criteria_order"] == ["zeta", "alpha", "mida"]


def test_cli_decide_score_y_noul():
    code, s = _run(
        "decide", "--question", "p", "--type", "score",
        "--criteria", "bajo", "medio", "alto",
    )
    assert code == 0 and 1.0 <= s["expected"] <= 3.0

    code, n = _run(
        "decide", "--question", "p", "--type", "noul",
        "--criteria", "bloquear", "monitorizar",
    )
    assert code == 0 and n["action"] in ("bloquear", "monitorizar")


def test_cli_decide_estado_json():
    code, body = _run(
        "decide", "--question", "p", "--criteria", "a", "b",
        "--state", json.dumps({"ip": "10.0.0.1"}),
    )
    assert code == 0


def test_cli_compare():
    code, body = _run(
        "compare", "--question", "p", "--criteria", "a", "b"
    )
    # mock siempre responde; laya puede fallar si no hay servidor local.
    assert code == 0
    assert "mock" in body["results"]


def test_cli_serve_help_no_arranca():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(["serve", "--help"])
    assert code == 0
