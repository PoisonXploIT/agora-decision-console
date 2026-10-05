"""Tests del contrato de orden (F0): criteria posicionales, sin sort_keys."""
from __future__ import annotations

import json

import pytest

from agora_core.contract import (
    ContractError,
    build_trace,
    canonical_criteria,
    serialize,
    validate_decision,
    validate_question,
)
from agora_core.schemas import Decision, Question, QuestionType


def _q(criteria, qtype="choice", id="q1") -> Question:
    return Question(id=id, type=qtype, prompt="p", criteria=list(criteria))


def test_orden_canonico_es_el_escrito():
    q = _q(["zeta", "alpha", "mida"])
    assert canonical_criteria(q) == ("zeta", "alpha", "mida")


def test_orden_canonico_rechaza_duplicados():
    q = Question.model_construct(
        id="q1", type="choice", prompt="p", criteria=["a", "b", "a"]
    )
    with pytest.raises(ContractError):
        canonical_criteria(q)


def test_serialize_no_ordena_claves():
    """La serializacion conserva el orden de insercion (no sort_keys)."""
    obj = {"z": 1, "a": 2, "m": 3}
    s = serialize(obj)
    assert s == '{"z": 1, "a": 2, "m": 3}'
    # y al reparsear sigue el mismo orden
    assert list(json.loads(s)) == ["z", "a", "m"]


def test_serialize_utf8_sin_escapes():
    s = serialize({"texto": "cañon — acción"})
    assert "cañon" in s and "\\u" not in s


def test_validate_question_ok_y_fallida():
    q = _q(["a", "b"])
    validate_question(q)  # no lanza
    qdup = Question.model_construct(
        id="q1", type="choice", prompt="p", criteria=["a", "a"]
    )
    with pytest.raises(ContractError):
        validate_question(qdup)
    qv = Question.model_construct(
        id="q", type="choice", prompt="", criteria=["a"]
    )
    with pytest.raises(ContractError):
        validate_question(qv)


def test_validate_decision_ordenes_distintos_no_mismo():
    """Claves iguales con otro orden es una infraccion: son posicionales."""
    q = _q(["b", "a"])
    ok = Decision(
        question_id=q.id, type=QuestionType.CHOICE,
        probabilities={"b": 0.6, "a": 0.4},
        trace=_trace(q),
    )
    validate_decision(ok, q)  # no lanza

    mal = Decision(
        question_id=q.id, type=QuestionType.CHOICE,
        probabilities={"a": 0.4, "b": 0.6},
        trace=_trace(q),
    )
    with pytest.raises(ContractError):
        validate_decision(mal, q)


def test_validate_decision_suma_uno():
    q = _q(["a", "b"])
    mal = Decision(
        question_id=q.id, type=QuestionType.CHOICE,
        probabilities={"a": 0.6, "b": 0.5},
        trace=_trace(q),
    )
    with pytest.raises(ContractError):
        validate_decision(mal, q)


def test_validate_decision_rango_de_probabilidades():
    q = _q(["a", "b"])
    mal = Decision(
        question_id=q.id, type=QuestionType.CHOICE,
        probabilities={"a": 1.2, "b": -0.2},
        trace=_trace(q),
    )
    with pytest.raises(ContractError):
        validate_decision(mal, q)


def test_validate_decision_score_esperado_en_rango():
    q = _q(["bajo", "medio", "alto"], qtype="score")
    ok = Decision(
        question_id=q.id, type=QuestionType.SCORE,
        probabilities={"bajo": 0.5, "medio": 0.3, "alto": 0.2},
        expected=1.8, trace=_trace(q),
    )
    validate_decision(ok, q)

    mal = Decision(
        question_id=q.id, type=QuestionType.SCORE,
        probabilities={"bajo": 0.5, "medio": 0.3, "alto": 0.2},
        expected=4.0, trace=_trace(q),
    )
    with pytest.raises(ContractError):
        validate_decision(mal, q)


def test_validate_decision_noul_accion_valida():
    q = _q(["bloquear", "monitorizar"], qtype="noul")
    ok = Decision(
        question_id=q.id, type=QuestionType.NOUL,
        probabilities={"bloquear": 0.7, "monitorizar": 0.3},
        action="bloquear", text="x", trace=_trace(q),
    )
    validate_decision(ok, q)

    mal = Decision(
        question_id=q.id, type=QuestionType.NOUL,
        probabilities={"bloquear": 0.7, "monitorizar": 0.3},
        action="rebootear", trace=_trace(q),
    )
    with pytest.raises(ContractError):
        validate_decision(mal, q)


def test_build_trace_con_orden_canonico():
    q = _q(["zeta", "alpha"])
    t = build_trace("mock", "mock-1", "local", 2.0, q, raw="{}")
    assert t["criteria_order"] == ["zeta", "alpha"]


def _trace(q: Question):
    from agora_core.schemas import Trace

    return Trace(
        backend="mock", model="mock-1", privacy="local", latency_ms=0.0,
        criteria_order=list(canonical_criteria(q)), raw="",
    )
