"""MockAdapter: backend determinista sin red, para tests y desarrollo.

La distribucion se deriva por hash de (pregunta + estado) serializados con la
serializacion canonica (sin ordenar claves): misma entrada, misma salida.
"""
from __future__ import annotations

import math

from agora_core.contract import serialize
from agora_core.schemas import Decision, DecisionRequest, QuestionType

from .base import BackendAdapter


class MockAdapter(BackendAdapter):
    """Determinista: hash estable de pregunta+estado -> softmax sobre criterios."""

    name = "mock"
    kind = "mock"
    privacy = "local"
    local = True

    def capabilities(self) -> list[QuestionType]:
        return [QuestionType.CHOICE, QuestionType.SCORE, QuestionType.NOUL]

    def decide(self, request: DecisionRequest) -> Decision:  # noqa: F821
        q = request.question
        seed = serialize(
            {"question": q.model_dump(), "state": request.state}
        )
        scores: list[float] = []
        for c in q.criteria:
            h = self._stable(seed + "|" + c)
            # puntuaciones en [1, 4): suficiente dispersion para que el
            # argmax dependa de la entrada y no sea siempre el primero.
            scores.append(1.0 + (h % 3_000_000) / 1_000_000.0 * 3.0)
        probs = self._softmax(scores)
        probs = dict(zip(q.criteria, probs))
        return self._finish(
            request, probs, model="mock-1", latency_ms=0.0, raw=seed[:200]
        )

    @staticmethod
    def _stable(text: str) -> int:
        import hashlib

        return int.from_bytes(
            hashlib.sha256(text.encode("utf-8")).digest()[:4], "big"
        )

    @staticmethod
    def _softmax(scores: list[float]) -> list[float]:
        m = max(scores)
        exps = [math.exp(s - m) for s in scores]
        total = sum(exps)
        return [e / total for e in exps]
