"""LayaAdapter: backend local LAYA por HTTP (laya-serve en 127.0.0.1:8787).

Protocolo simple sobre HTTP POST ``/v1/decide``:

    -> {"question": {...}, "state": ...}
    <- {"probabilities": [..] | {criterio: p},
        "expected"?: float, "action"?: str, "text"?: str, "model"?: str}

Sin nube: solo contra el servidor local.
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


class LayaAdapter(BackendAdapter):
    """Adaptador HTTP a laya-serve (local)."""

    kind = "laya"
    privacy = "local"

    def __init__(self, base_url: str = "http://127.0.0.1:8787", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        host = base_url.split("//")[-1].split(":")[0]
        self.local = host in ("127.0.0.1", "localhost", "::1")
        self.name = "laya"

    def capabilities(self) -> list[QuestionType]:
        return [QuestionType.CHOICE, QuestionType.SCORE, QuestionType.NOUL]

    def decide(self, request: DecisionRequest) -> Decision:
        q = request.question
        payload = json.dumps(
            {"question": q.model_dump(), "state": request.state},
            ensure_ascii=False,
        )
        req = urllib.request.Request(
            self.base_url + "/v1/decide",
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise AdapterError(
                f"no se pudo hablar con LAYA en {self.base_url}: {e}"
            ) from e
        latency_ms = (time.monotonic() - t0) * 1000.0

        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise AdapterError(f"respuesta no-JSON de LAYA: {body[:200]!r}") from e
        if not isinstance(data, dict) or "probabilities" not in data:
            raise AdapterError(f"respuesta sin 'probabilities': {body[:200]!r}")

        probs = normalize_probabilities(q, data["probabilities"])
        expected = data.get("expected")
        action = data.get("action")
        text = data.get("text")
        if q.type is QuestionType.SCORE:
            expected = (
                float(expected) if expected is not None else round(expected_from_probs(probs), 6)
            )
        if q.type is QuestionType.NOUL:
            action = str(action) if action is not None else argmax(probs)
            text = (
                str(text)
                if text is not None
                else f"laya elige {action!r} (p={probs[action]:.3f})"
            )
        decision = self._finish(
            request,
            probs,
            model=str(data.get("model", "laya")),
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
