"""Contrato de decision de AGORA.

Pieza critica: los `criteria` son POSICIONALES. El orden canonico es el orden
en que aparecen en la pregunta; nunca se ordenan por clave y la serializacion
no usa sort_keys. Todo lo que salga (probabilidades, traza, ficheros) debe
respetar ese orden.
"""
from __future__ import annotations

import json
from typing import Any

from .schemas import Decision, Question, QuestionType


class ContractError(ValueError):
    """Infraccion del contrato de decision."""


def canonical_criteria(question: Question) -> tuple[str, ...]:
    """Orden canonico de los criterios: el orden escrito en la pregunta.

    Nunca se reordena ni se dedupla silenciosamente: si hay duplicados es un
    error de contrato (la pregunta no seria un juicio atomico bien formado).
    """
    criteria = list(question.criteria)
    if len(set(criteria)) != len(criteria):
        raise ContractError(
            f"criterios duplicados en la pregunta {question.id!r}: {criteria!r}"
        )
    return tuple(criteria)


def serialize(obj: Any) -> str:
    """Serializacion canonica de AGORA: NO ordena claves.

    json.dumps sin sort_keys, UTF-8 sin escapes. El orden de insercion del
    dict (que para las probabilidades es el orden canonico de criterios) se
    conserva tal cual.
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=False)


def validate_question(question: Question) -> None:
    """Valida que la pregunta cumple el contrato antes de decidir."""
    if not question.id.strip():
        raise ContractError("la pregunta necesita un id no vacio")
    if not question.prompt.strip():
        raise ContractError(f"la pregunta {question.id!r} no tiene prompt")
    canonical_criteria(question)  # lanza si hay duplicados


def validate_decision(decision: Decision, question: Question) -> None:
    """Valida una decision contra su pregunta.

    - las claves de `probabilities` son exactamente los criterios, en orden
      canonico (posicional);
    - cada probabilidad esta en [0, 1] y la suma es 1 (tolerancia 1e-6);
    - score lleva `expected` dentro de [1, N];
    - noul lleva `action` entre los criterios.
    """
    canon = canonical_criteria(question)
    if tuple(decision.probabilities.keys()) != canon:
        raise ContractError(
            "las probabilidades no siguen el orden canonico de criterios: "
            f"esperado {canon!r}, recibido {tuple(decision.probabilities)!r}"
        )
    total = 0.0
    for name, p in decision.probabilities.items():
        if not (0.0 <= p <= 1.0):
            raise ContractError(f"probabilidad fuera de [0,1] en {name!r}: {p}")
        total += p
    if abs(total - 1.0) > 1e-6:
        raise ContractError(f"las probabilidades suman {total}, no 1")

    if decision.type is not question.type:
        raise ContractError(
            f"el tipo de la decision ({decision.type}) no es el de la pregunta "
            f"({question.type})"
        )
    n = len(canon)
    if question.type is QuestionType.SCORE:
        if decision.expected is None or not (1.0 <= decision.expected <= float(n)):
            raise ContractError(
                f"score: expected debe estar en [1, {n}], recibido "
                f"{decision.expected!r}"
            )
    if question.type is QuestionType.NOUL:
        if decision.action is None or decision.action not in canon:
            raise ContractError(
                f"noul: action debe ser uno de {canon!r}, recibido "
                f"{decision.action!r}"
            )


def build_trace(
    backend: str,
    model: str,
    privacy: str,
    latency_ms: float,
    question: Question,
    raw: str,
) -> dict[str, Any]:
    """Datos de traza con el orden canonico ya puesto (para construir Trace)."""
    return {
        "backend": backend,
        "model": model,
        "privacy": privacy,
        "latency_ms": latency_ms,
        "criteria_order": list(canonical_criteria(question)),
        "raw": raw,
    }
