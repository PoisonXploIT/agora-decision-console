"""EikosAdapter: backend local Eikos por HTTP (serve.py).

Protocolo simple sobre HTTP POST ``/v1/decide``:

    -> {"question": {...}, "state": ..., "images"?: [base64, ...]}
    <- {"probabilities": [..] | {criterio: p},
        "expected"?: float, "action"?: str, "text"?: str, "model"?: str}

``images`` es opcional: base64 de imagenes que el modelo local puede ver
(Eikos con vision). Sin nube: solo contra el servidor local.

Guia de arranque del Eikos local en ``docs/eikos-local.md`` (Eikos-4B cabe
en 16 GB; Eikos-27B INT4 son 19,4 GB y no caben).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from agora_core.contract import validate_decision
from agora_core.schemas import (  # noqa: F401
    Decision,
    DecisionRequest,
    QuestionType,
)
from .base import (
    AdapterError,
    BackendAdapter,
    argmax,
    expected_from_probs,
    normalize_probabilities,
)


class EikosAdapter(BackendAdapter):
    """Adaptador HTTP a serve.py de Eikos (local)."""

    kind = "eikos"
    privacy = "local"

    def __init__(self, base_url: str = "http://127.0.0.1:8901", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        host = base_url.split("//")[-1].split(":")[0]
        self.local = host in ("127.0.0.1", "localhost", "::1")
        self.name = "eikos"

    def capabilities(self) -> list[QuestionType]:
        return [QuestionType.CHOICE, QuestionType.SCORE, QuestionType.NOUL]

    def decide(
        self,
        request: DecisionRequest,
        images: list[str] | None = None,
    ) -> Decision:
        """Decide contra el servidor Eikos; ``images`` son base64 opcionales."""
        q = request.question
        payload: dict = {"question": q.model_dump(), "state": request.state}
        if images:
            payload["images"] = list(images)

        req = urllib.request.Request(
            self.base_url + "/v1/decide",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise AdapterError(
                f"no se pudo hablar con Eikos en {self.base_url}: {e}"
            ) from e
        latency_ms = (time.monotonic() - t0) * 1000.0

        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise AdapterError(f"respuesta no-JSON de Eikos: {body[:200]!r}") from e
        if not isinstance(data, dict) or "probabilities" not in data:
            raise AdapterError(f"respuesta sin 'probabilities': {body[:200]!r}")

        probs = normalize_probabilities(q, data["probabilities"])
        expected = data.get("expected")
        action = data.get("action")
        text = data.get("text")
        if q.type is QuestionType.SCORE:
            expected = (
                float(expected)
                if expected is not None
                else round(expected_from_probs(probs), 6)
            )
        if q.type is QuestionType.NOUL:
            action = str(action) if action is not None else argmax(probs)
            text = (
                str(text)
                if text is not None
                else f"eikos elige {action!r} (p={probs[action]:.3f})"
            )
        decision = self._finish(
            request,
            probs,
            model=str(data.get("model", "eikos")),
            latency_ms=latency_ms,
            raw=body[:4000],
        )
        # el servidor puede refinar expected/action/text; se revalidan.
        if q.type is QuestionType.SCORE and expected is not None:
            decision.expected = float(expected)
        if q.type is QuestionType.NOUL and action is not None:
            decision.action = str(action)
        if q.type is QuestionType.NOUL and text is not None:
            decision.text = str(text)
        validate_decision(decision, q)
        return decision
