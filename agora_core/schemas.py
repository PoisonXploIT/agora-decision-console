"""Esquemas tipados de AGORA (pydantic v2).

Tres tipos de pregunta, todos atomicos:

- choice : distribucion calibrada sobre `criteria` (posicionales).
- score  : escala ordinal de N niveles; `criteria` son las etiquetas de nivel
            en orden ascendente. Devuelve la distribucion y el valor esperado.
- noul   : accion inmediata en lenguaje natural; `criteria` son las acciones
            candidatas, se devuelve la distribucion, la accion elegida (argmax)
            y un texto justificativo.

El estado (`DecisionRequest.state`) es contenido no confiable: viaja como dato
y nunca se interpreta como instruccion.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class QuestionType(str, Enum):
    CHOICE = "choice"
    SCORE = "score"
    NOUL = "noul"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Question(BaseModel):
    """Una pregunta es un juicio atomico.

    `criteria` son POSICIONALES: el orden en que se escriben es el orden
    canonico de la respuesta. Nunca se reordenan.
    """

    id: str = Field(min_length=1)
    type: QuestionType
    prompt: str = Field(min_length=1)
    criteria: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_criteria(self) -> Question:
        for c in self.criteria:
            if not isinstance(c, str) or not c.strip():
                raise ValueError("cada criterio debe ser un texto no vacio")
        if len(set(self.criteria)) != len(self.criteria):
            raise ValueError("los criterios no pueden repetirse")
        if self.type is QuestionType.SCORE and len(self.criteria) < 2:
            raise ValueError("score necesita al menos dos niveles")
        return self


class DecisionRequest(BaseModel):
    """Pregunta + estado. El estado es contenido no confiable (dato, no orden)."""

    state: Any = Field(default_factory=dict)
    question: Question
    backend: str | None = None
    request_id: str = Field(default_factory=lambda: uuid4().hex)


class Trace(BaseModel):
    """Trazabilidad de una decision: backend, modelo, latencia y orden canonico."""

    backend: str
    model: str
    privacy: str  # "local" | "cloud"
    latency_ms: float = Field(ge=0)
    criteria_order: list[str]
    raw: str
    created_at: str = Field(default_factory=_now_iso)


class Decision(BaseModel):
    """Salida normalizada por tipo de pregunta.

    - choice/score/noul: `probabilities` con claves en orden canonico (igual que
      `trace.criteria_order`).
    - score: ademas `expected` (valor esperado sobre 1..N).
    - noul: ademas `action` (argmax) y `text` (justificacion breve).
    """

    question_id: str
    type: QuestionType
    probabilities: dict[str, float] = Field(description="claves en orden canonico")
    expected: float | None = None
    action: str | None = None
    text: str | None = None
    trace: Trace


class BackendInfo(BaseModel):
    """Ficha publica de un backend (endpoint /backends)."""

    name: str
    kind: str  # "mock" | "laya" | "jev" | "eikos"
    privacy: str  # "local" | "cloud"
    local: bool
    base_url: str | None = None
    supports: list[QuestionType]
