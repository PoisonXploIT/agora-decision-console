"""Base comun de los adaptadores de backend de AGORA.

Un adaptador es una clase con dos responsabilidades:

- ``capabilities()`` : que tipos de pregunta (choice/score/noul) soporta.
- ``decide(request)`` : recibe un ``DecisionRequest`` y devuelve una
  ``Decision`` normalizada por tipo, con su ``Trace`` (backend, modelo,
  latencia y ``criteria_order`` en orden canonico).

Los criterios son POSICIONALES: la salida normalizada siempre pone las
probabilidades con las claves en el orden canonico de la pregunta.
"""
from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Any

from agora_core.contract import build_trace, validate_decision
from agora_core.schemas import (
    BackendInfo,
    Decision,
    DecisionRequest,
    Question,
    QuestionType,
    Trace,
)


class AdapterError(RuntimeError):
    """El backend devolvio algo que no cumple el contrato de decision."""


def normalize_probabilities(question: Question, raw: Any) -> dict[str, float]:
    """Normaliza la salida cruda de un backend a probabilidades canonicas.

    ``raw`` puede ser:

    - una lista/tupla alineada por posicion con los criterios (orden canonico), o
    - un dict {criterio: probabilidad} (se reordena al orden canonico).

    El resultado siempre es un dict con las claves en orden canonico y suma 1.
    """
    criteria = list(question.criteria)
    if isinstance(raw, dict):
        values: dict[str, float] = {}
        for name in criteria:
            if name not in raw:
                raise AdapterError(
                    f"el backend no devolvio probabilidad para el criterio {name!r}"
                )
            values[name] = float(raw[name])
    else:
        try:
            items = list(raw)
        except TypeError as e:
            raise AdapterError(f"salida cruda no normalizable: {raw!r}") from e
        if len(items) != len(criteria):
            raise AdapterError(
                f"el backend devolvio {len(items)} valores para "
                f"{len(criteria)} criterios"
            )
        values = {name: float(p) for name, p in zip(criteria, items)}

    total = sum(values.values())
    if total <= 0 or any(p < 0 for p in values.values()):
        raise AdapterError(f"probabilidades no validas (suma {total}): {values!r}")
    return {name: p / total for name, p in values.items()}


def make_decision(
    request: DecisionRequest,
    probs: dict[str, float],
    *,
    backend: str,
    model: str,
    privacy: str,
    latency_ms: float,
    raw: str,
    expected: float | None = None,
    action: str | None = None,
    text: str | None = None,
) -> Decision:
    """Construye una ``Decision`` normalizada y la valida contra el contrato.

    ``probs`` debe tener las claves en orden canonico (como lo garantiza
    :func:`normalize_probabilities`).
    """
    q = request.question
    decision = Decision(
        question_id=q.id,
        type=q.type,
        probabilities=dict(probs),
        expected=expected,
        action=action,
        text=text,
        trace=Trace(**build_trace(backend, model, privacy, latency_ms, q, raw)),
    )
    validate_decision(decision, q)
    return decision


def expected_from_probs(probs: dict[str, float]) -> float:
    """Valor esperado de una escala ordinal 1..N sobre probabilidades."""
    n = len(probs)
    return sum((i + 1) * p for i, p in enumerate(probs.values()))


def argmax(probs: dict[str, float]) -> str:
    """Criterio con maxima probabilidad (empates: el primero en orden canonico)."""
    best_name, best_p = None, -1.0
    for name, p in probs.items():
        if p > best_p:
            best_name, best_p = name, p
    assert best_name is not None
    return best_name


def stable_hash(text: str) -> int:
    """Hash estable (SHA-256) de un texto; 32 bits."""
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")


class BackendAdapter(ABC):
    """Base comun: ``capabilities`` y ``decide``."""

    name: str = "base"
    kind: str = "base"
    privacy: str = "local"  # "local" | "cloud"
    local: bool = True

    @abstractmethod
    def capabilities(self) -> list[QuestionType]:
        """Tipos de pregunta que soporta este backend."""

    @abstractmethod
    def decide(self, request: DecisionRequest) -> Decision:
        """Devuelve una ``Decision`` normalizada (orden canonico + Trace)."""

    def info(self) -> BackendInfo:
        return BackendInfo(
            name=self.name,
            kind=self.kind,
            privacy=self.privacy,
            local=self.local,
            base_url=getattr(self, "base_url", None),
            supports=list(self.capabilities()),
        )

    # --- utilidades compartidas -------------------------------------------

    def _finish(
        self,
        request: DecisionRequest,
        probs: dict[str, float],
        *,
        model: str,
        latency_ms: float,
        raw: str,
    ) -> Decision:
        q = request.question
        expected = None
        action = None
        text = None
        if q.type is QuestionType.SCORE:
            expected = round(expected_from_probs(probs), 6)
        if q.type is QuestionType.NOUL:
            action = argmax(probs)
            p = probs[action]
            text = f"{self.name} elige {action!r} (p={p:.3f})"
        return make_decision(
            request,
            probs,
            backend=self.name,
            model=model,
            privacy=self.privacy,
            latency_ms=latency_ms,
            raw=raw,
            expected=expected,
            action=action,
            text=text,
        )
