"""LayaAdapter: backend local LAYA por HTTP (laya-serve en 127.0.0.1:8787).

Habla la API compatible TypeSafe que expone ``laya-serve``:

    POST /v1/systemone
    -> {"state": <dato>, "questions": {"<id>": {"type","instructions","criteria"}}}
    <- {"model": "...", "answers": {"<id>": {...}}, "usage": {...}, "routing": {...}}

La respuesta es por pregunta:

- choice : ``{"choice","probabilities"{criterio: p},"confidence"}``
- score  : ``{"score","legend","probabilities"{"0": p0, "1": p1, ...},"confidence"}``
- noul   : ``{"noul": p}`` (y a veces ``probabilities``)

El adaptador convierte todo a la ``Decision`` normalizada de AGORA, con las
probabilidades en ORDEN CANONICO (el de ``question.criteria``).

Auth: ``laya-serve`` exige bearer. La clave se toma de ``api_key`` o de la
variable de entorno ``LAYA_API_KEY``. Sin clave, el servidor devuelve 401.

Sin nube: solo se habla con el host de ``base_url``.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from agora_core.contract import validate_decision
from agora_core.schemas import (
    Decision,
    DecisionRequest,
    Question,
    QuestionType,
)
from .base import (
    AdapterError,
    BackendAdapter,
    argmax,
)


class LayaAdapter(BackendAdapter):
    """Adaptador HTTP a laya-serve (local, API /v1/systemone)."""

    kind = "laya"
    privacy = "local"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8787",
        timeout: float = 120.0,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key if api_key is not None else os.environ.get("LAYA_API_KEY", "")
        self.model = model
        host = self.base_url.split("//")[-1].split(":")[0]
        self.local = host in ("127.0.0.1", "localhost", "::1")
        self.privacy = "local" if self.local else "cloud"
        self.name = "laya"

    def capabilities(self) -> list[QuestionType]:
        return [QuestionType.CHOICE, QuestionType.SCORE, QuestionType.NOUL]

    # --- construccion del payload -----------------------------------------

    @staticmethod
    def _question_payload(q: Question) -> dict:
        """Traduce una ``Question`` de AGORA al formato de laya-serve."""
        if q.type is QuestionType.CHOICE:
            # laya espera un mapa criterio -> descripcion; conservamos el orden.
            criteria = {name: name for name in q.criteria}
            return {"type": "choice", "instructions": q.prompt, "criteria": criteria}
        if q.type is QuestionType.SCORE:
            return {"type": "score", "instructions": q.prompt, "criteria": list(q.criteria)}
        # noul: dos criterios (si/no). El resto no es representable.
        if len(q.criteria) == 2:
            return {
                "type": "noul",
                "instructions": q.prompt,
                "criteria": {q.criteria[0]: q.criteria[0], q.criteria[1]: q.criteria[1]},
            }
        return {"type": "noul", "instructions": q.prompt}

    # --- parseo de la respuesta -------------------------------------------

    @staticmethod
    def _probs(q: Question, ans: dict) -> list[float]:
        """Probabilidades en el ORDEN CANONICO de la pregunta (lista)."""
        if q.type is QuestionType.CHOICE:
            probs = ans.get("probabilities")
            if not isinstance(probs, dict):
                raise AdapterError(f"choice sin 'probabilities': {str(ans)[:200]}")
            return [float(probs[name]) for name in q.criteria]
        if q.type is QuestionType.SCORE:
            probs = ans.get("probabilities")
            if not isinstance(probs, dict):
                raise AdapterError(f"score sin 'probabilities': {str(ans)[:200]}")
            # claves "0".."N-1" alineadas con los niveles en orden.
            return [float(probs[str(i)]) for i in range(len(q.criteria))]
        # noul
        if "noul" in ans:
            p = float(ans["noul"])
            return [p, 1.0 - p]
        probs = ans.get("probabilities")
        if isinstance(probs, dict) and len(probs) == 2:
            vals = list(probs.values())
            return [float(vals[0]), float(vals[1])]
        raise AdapterError(f"noul sin 'noul' ni 'probabilities': {str(ans)[:200]}")

    # --- llamada ----------------------------------------------------------

    def decide(self, request: DecisionRequest) -> Decision:
        q = request.question
        payload_obj: dict = {
            "state": request.state,
            "questions": {q.id: self._question_payload(q)},
        }
        if self.model:
            # La API cloud (TypeSafe/JEV) exige 'model'; laya-serve lo ignora.
            payload_obj["model"] = self.model
        payload = json.dumps(payload_obj, ensure_ascii=False)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(
            self.base_url + "/v1/systemone",
            data=payload.encode("utf-8"),
            headers=headers,
            method="POST",
        )

        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            raise AdapterError(f"{self.name} respondio HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise AdapterError(f"no se pudo hablar con LAYA en {self.base_url}: {e}") from e
        latency_ms = (time.monotonic() - t0) * 1000.0

        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise AdapterError(f"respuesta no-JSON de LAYA: {body[:200]!r}") from e
        answers = data.get("answers") if isinstance(data, dict) else None
        if not isinstance(answers, dict) or q.id not in answers:
            raise AdapterError(f"{self.name}: respuesta sin 'answers[{q.id}]': {body[:200]!r}")

        probs = self._probs(q, answers[q.id] or {})
        model = str(data.get("model") or self.model or "laya")
        decision = self._finish(request, dict(zip(q.criteria, probs)), model=model,
                                latency_ms=latency_ms, raw=body[:4000])
        return decision


__all__ = ["LayaAdapter", "AdapterError", "validate_decision", "argmax"]
