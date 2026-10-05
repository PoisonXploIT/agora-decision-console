"""agora_core - esquemas tipados y contrato de decision de AGORA.

Modulos:
    schemas  - modelos pydantic (Question, DecisionRequest, Trace, Decision)
    contract - orden canonico de criterios, serializacion sin reordenar y
               validacion de preguntas y decisiones

El contrato de orden es la pieza critica: los criteria son posicionales y su
orden canonico es el orden en que se escriben en la pregunta.
"""
from .contract import (
    ContractError,
    build_trace,
    canonical_criteria,
    serialize,
    validate_decision,
    validate_question,
)
from .schemas import (
    BackendInfo,
    Decision,
    DecisionRequest,
    Question,
    QuestionType,
    Trace,
)

__version__ = "0.0.1"

__all__ = [
    "BackendInfo",
    "ContractError",
    "Decision",
    "DecisionRequest",
    "Question",
    "QuestionType",
    "Trace",
    "build_trace",
    "canonical_criteria",
    "serialize",
    "validate_decision",
    "validate_question",
    "__version__",
]
