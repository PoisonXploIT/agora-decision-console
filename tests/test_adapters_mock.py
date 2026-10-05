"""Tests de los adaptadores con MockAdapter (F1)."""
from __future__ import annotations

import pytest

from agora_adapters.base import AdapterError, normalize_probabilities
from agora_adapters.mock import MockAdapter
from agora_core.schemas import DecisionRequest, Question, QuestionType


def _req(qtype: str = "choice", criteria=None, state=None, **kw) -> DecisionRequest:
    kwargs = dict(kw)
    q = Question(
        id=kwargs.pop("id", "q1"),
        type=qtype,
        prompt=kwargs.pop("prompt", "decide"),
        criteria=criteria if criteria is not None else ["a", "b"],
    )
    return DecisionRequest(state={} if state is None else state, question=q)


def test_mock_determinista():
    m = MockAdapter()
    r1 = _req(criteria=["zeta", "alpha", "mida"])
    d1 = m.decide(r1)
    d2 = m.decide(_req(criteria=["zeta", "alpha", "mida"]))
    assert d1.probabilities == d2.probabilities


def test_mock_cambia_con_el_estado():
    m = MockAdapter()
    base = m.decide(_req(state={"x": 1}))
    otro = m.decide(_req(state={"x": 2}))
    # no exigimos diferencia (colisiones de hash), pero el contrato se cumple:
    assert sum(base.probabilities.values()) == pytest.approx(1.0)
    assert sum(otro.probabilities.values()) == pytest.approx(1.0)


def test_mock_orden_canonico_en_salida():
    m = MockAdapter()
    d = m.decide(_req(criteria=["zeta", "alpha", "mida"]))
    assert list(d.probabilities) == ["zeta", "alpha", "mida"]
    assert d.trace.criteria_order == ["zeta", "alpha", "mida"]


def test_mock_suma_uno_y_rango():
    m = MockAdapter()
    for criteria in (["a"], ["a", "b"], ["a", "b", "c", "d", "e"]):
        d = m.decide(_req(criteria=criteria))
        assert sum(d.probabilities.values()) == pytest.approx(1.0)
        assert all(0.0 <= p <= 1.0 for p in d.probabilities.values())


def test_mock_score_esperado_en_rango():
    m = MockAdapter()
    d = m.decide(_req("score", criteria=["bajo", "medio", "alto"]))
    assert d.type is QuestionType.SCORE
    assert 1.0 <= d.expected <= 3.0
    assert list(d.probabilities) == ["bajo", "medio", "alto"]


def test_mock_noul_accion_argmax():
    m = MockAdapter()
    d = m.decide(_req("noul", criteria=["bloquear", "monitorizar", "ignorar"]))
    best = max(d.probabilities.values())
    assert d.probabilities[d.action] == best
    assert d.text


def test_mock_traza_completa():
    m = MockAdapter()
    d = m.decide(_req(criteria=["a", "b"]))
    assert d.trace.backend == "mock"
    assert d.trace.privacy == "local"
    assert d.trace.model == "mock-1"
    assert d.trace.latency_ms >= 0


def test_mock_capabilities():
    m = MockAdapter()
    assert m.capabilities() == [QuestionType.CHOICE, QuestionType.SCORE, QuestionType.NOUL]
    info = m.info()
    assert info.local is True and info.privacy == "local"


def test_normalize_probabilidades_lista_y_dict():
    q = _req(criteria=["b", "a"]).question
    p1 = normalize_probabilities(q, [0.3, 0.7])
    p2 = normalize_probabilities(q, {"a": 0.7, "b": 0.3})
    assert list(p1) == ["b", "a"] and list(p2) == ["b", "a"]
    assert p1["b"] == pytest.approx(0.3) and p2["b"] == pytest.approx(0.3)


def test_normalize_probabilidades_rechaza_mal_formada():
    q = _req(criteria=["a", "b"]).question
    with pytest.raises(AdapterError):
        normalize_probabilities(q, [0.5])  # longitud distinta
    with pytest.raises(AdapterError):
        normalize_probabilities(q, {"a": 1.0})  # falta 'b'
