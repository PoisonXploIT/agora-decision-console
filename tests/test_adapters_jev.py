"""Tests del JevAdapter contra un servidor falso local (F2)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fakes"))

from fake_openai_server import FakeOpenAIServer  # noqa: E402

from agora_adapters.jev import JevAdapter
from agora_core.schemas import DecisionRequest, Question, QuestionType


@pytest.fixture(scope="module")
def server():
    srv = FakeOpenAIServer().start()
    yield srv
    srv.stop()


def _req(qtype: str = "choice", criteria=None) -> DecisionRequest:
    q = Question(
        id="q-jev", type=qtype, prompt="decide con JEV",
        criteria=criteria if criteria is not None else ["a", "b"],
    )
    return DecisionRequest(state={"ctx": 1}, question=q)


def test_jev_decide_contra_servidor_falso(server):
    ad = JevAdapter(base_url=server.url)
    d = ad.decide(_req(criteria=["zeta", "alpha", "mida"]))
    assert list(d.probabilities) == ["zeta", "alpha", "mida"]
    assert sum(d.probabilities.values()) == pytest.approx(1.0)
    assert d.trace.backend == "jev"
    assert d.trace.privacy == "cloud"
    assert d.trace.criteria_order == ["zeta", "alpha", "mida"]


def test_jev_determinista(server):
    ad = JevAdapter(base_url=server.url)
    a = ad.decide(_req(criteria=["a", "b", "c"]))
    b = ad.decide(_req(criteria=["a", "b", "c"]))
    assert a.probabilities == b.probabilities


def test_jev_score_y_noul(server):
    ad = JevAdapter(base_url=server.url)
    s = ad.decide(_req("score", criteria=["bajo", "medio", "alto"]))
    assert s.type is QuestionType.SCORE and 1.0 <= s.expected <= 3.0
    n = ad.decide(_req("noul", criteria=["bloquear", "monitorizar"]))
    assert n.action in ("bloquear", "monitorizar") and n.text


def test_jev_dry_run_sin_red():
    """dry_run decide sin tocar la red: base_url muerta y no lanza."""
    ad = JevAdapter(base_url="http://127.0.0.1:1", dry_run=True)
    d = ad.decide(_req(criteria=["a", "b"]))
    assert sum(d.probabilities.values()) == pytest.approx(1.0)
    assert "dry-run" in d.trace.raw
    assert d.trace.privacy == "cloud"


def test_jev_dry_run_determinista():
    ad = JevAdapter(base_url="http://127.0.0.1:1", dry_run=True)
    a = ad.decide(_req(criteria=["a", "b", "c"]))
    b = ad.decide(_req(criteria=["a", "b", "c"]))
    assert a.probabilities == b.probabilities


def test_jev_info_privacy_cloud(server):
    ad = JevAdapter(base_url=server.url)
    info = ad.info()
    assert info.privacy == "cloud" and info.kind == "jev"
    assert set(info.supports) == {QuestionType.CHOICE, QuestionType.SCORE, QuestionType.NOUL}
