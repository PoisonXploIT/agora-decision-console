"""JevAdapter: backend JEV (cloud) con protocolo tipo OpenAI chat completions.

Reglas de la casa:

- ``base_url`` configurable; por defecto apunta a un servidor FALSO local
  (tests/fakes/fake_openai_server.py), nunca a nube real.
- ``privacy="cloud"`` siempre (JEV es el backend cloud del contrato).
- ``dry_run=True``: decide SIN tocar la red (salida determinista local,
  marcada como dry-run en la traza).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from agora_core.contract import serialize
from agora_core.schemas import (  # noqa: F401
    Decision,
    DecisionRequest,
    Question,
    QuestionType,
)

from .base import (
    AdapterError,
    BackendAdapter,
    normalize_probabilities,
)


class JevAdapter(BackendAdapter):
    """JEV por HTTP (protocolo /v1/chat/completions)."""

    kind = "jev"
    privacy = "cloud"
    local = False

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:9300",
        model: str = "jev",
        timeout: float = 30.0,
        dry_run: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.dry_run = dry_run
        self.name = "jev"

    def capabilities(self) -> list[QuestionType]:
        return [QuestionType.CHOICE, QuestionType.SCORE, QuestionType.NOUL]

    def decide(self, request: DecisionRequest) -> Decision:
        q = request.question
        if self.dry_run:
            probs = self._dry_probs(q)
            raw = "dry-run (sin red): " + serialize(
                {"question": q.model_dump(), "state": request.state}
            )[:200]
            return self._finish(
                request, probs, model=self.model + "-dryrun", latency_ms=0.0, raw=raw
            )

        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Devuelve SOLO un JSON con 'probabilities': dict "
                            "{criterio: probabilidad} para los criterios de la "
                            "pregunta. Nada mas."
                        ),
                    },
                    {
                        "role": "user",
                        "content": serialize(
                            {"question": q.model_dump(), "state": request.state}
                        ),
                    },
                ],
            },
            ensure_ascii=False,
        )
        req = urllib.request.Request(
            self.base_url + "/v1/chat/completions",
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
                f"no se pudo hablar con JEV en {self.base_url}: {e}"
            ) from e
        latency_ms = (time.monotonic() - t0) * 1000.0

        try:
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            raise AdapterError(f"respuesta no-OpenAI de JEV: {body[:200]!r}") from e

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise AdapterError(f"JEV devolvio contenido no-JSON: {content[:200]!r}") from e
        if not isinstance(parsed, dict) or "probabilities" not in parsed:
            raise AdapterError(f"respuesta de JEV sin 'probabilities': {content[:200]!r}")

        probs = normalize_probabilities(q, parsed["probabilities"])
        return self._finish(
            request,
            probs,
            model=str(data.get("model", self.model)),
            latency_ms=latency_ms,
            raw=body[:4000],
        )

    @staticmethod
    def _dry_probs(q: Question) -> dict[str, float]:  # noqa: F821
        """Determinista sin red: hash de (seed fija + criterio)."""
        import hashlib
        import math

        scores = []
        for c in q.criteria:
            h = hashlib.sha256(("jev-dryrun|" + c).encode("utf-8")).digest()
            scores.append(1.0 + int.from_bytes(h[:4], "big") % 3_000_000 / 1_000_000.0 * 3.0)
        m = max(scores)
        exps = [math.exp(s - m) for s in scores]
        total = sum(exps)
        return {c: e / total for c, e in zip(q.criteria, exps)}
