"""Tests del EikosAdapter contra un servidor falso local (F10)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fakes"))

from fake_eikos_server import FakeEikosServer  # noqa: E402

from agora_adapters.base import AdapterError
from agora_adapters.eikos import EikosAdapter
from agora_core.schemas import DecisionRequest, Question, QuestionType


@pytest.fixture(scope="module")
def server():
    srv = FakeEikosServer().start()
    yield srv
    srv.stop()


def _req(qtype: str = "choice", criteria=None) -> DecisionRequest:
    q = Question(
        id="q-eikos", type=qtype, prompt="decide con Eikos",
        criteria=criteria if criteria is not None else ["a", "b"],
    )
    return DecisionRequest(state={"ctx": 1}, question=q)


def test_eikos_decide_contra_servidor_falso(server):
    ad = EikosAdapter(base_url=server.url)
    d = ad.decide(_req(criteria=["zeta", "alpha", "mida"]))
    assert list(d.probabilities) == ["zeta", "alpha", "mida"]
    assert sum(d.probabilities.values()) == pytest.approx(1.0)
    assert d.trace.backend == "eikos"
    assert d.trace.privacy == "local"
    assert d.trace.criteria_order == ["zeta", "alpha", "mida"]


def test_eikos_determinista(server):
    ad = EikosAdapter(base_url=server.url)
    a = ad.decide(_req(criteria=["a", "b", "c"]))
    b = ad.decide(_req(criteria=["a", "b", "c"]))
    assert a.probabilities == b.probabilities


def test_eikos_score_y_noul(server):
    ad = EikosAdapter(base_url=server.url)
    s = ad.decide(_req("score", criteria=["bajo", "medio", "alto"]))
    assert s.type is QuestionType.SCORE and 1.0 <= s.expected <= 3.0
    n = ad.decide(_req("noul", criteria=["bloquear", "monitorizar"]))
    assert n.action in ("bloquear", "monitorizar") and n.text


def test_eikos_imagenes_opcionales(server):
    ad = EikosAdapter(base_url=server.url)
    d = ad.decide(_req(), images=["aGVsbG8="])
    assert list(d.probabilities) == ["a", "b"]
    assert server.last_images == ["aGVsbG8="]
    # sin imagenes no se envia ninguna
    ad.decide(_req())
    assert server.last_images == []


def test_eikos_info_privacy_local(server):
    info = EikosAdapter(base_url=server.url).info()
    assert info.privacy == "local" and info.kind == "eikos"
    assert set(info.supports) == {QuestionType.CHOICE, QuestionType.SCORE, QuestionType.NOUL}


def test_eikos_sin_servidor_lanza():
    ad = EikosAdapter(base_url="http://127.0.0.1:1", timeout=2.0)
    with pytest.raises(AdapterError):
        ad.decide(_req())
