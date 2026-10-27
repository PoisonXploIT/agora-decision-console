"""Tests del LLM de chat configurable y del flujo /v1/ask (lenguaje natural -> tipado).

Cubre dos cosas nuevas:

- ChatAdapter: cualquier LLM local compatible con OpenAI responde una pregunta
  tipada y su salida se normaliza a probabilidades canonicas.
- /v1/ask: el chat compila la pregunta y propone un backend; el codigo valida la
  propuesta y cae a un fallback determinista si no vale.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agora_adapters.chat import ChatAdapter, completions_url, models_url
from agora_core.schemas import DecisionRequest, Question
from agora_serve import chat_config, questions
from agora_serve.app import create_app


@pytest.fixture()
def client():
    c = TestClient(create_app())
    c.delete("/v1/runs")          # no contaminar el historial compartido
    yield c
    c.delete("/v1/runs")


# ------------------------------------------------------------ URLs

def test_completions_url_normaliza():
    assert completions_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080/v1/chat/completions"
    assert completions_url("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080/v1/chat/completions"
    assert models_url("http://127.0.0.1:8080/v1/chat/completions") == "http://127.0.0.1:8080/v1/models"


# ------------------------------------------------------------ ChatAdapter

class _FakeChat(ChatAdapter):
    """ChatAdapter con la red sustituida por una respuesta fija."""

    def __init__(self, respuesta: str):
        super().__init__(base_url="http://127.0.0.1:9999", model="fake-1")
        self._respuesta = respuesta

    def _post(self, messages):
        return self._respuesta

    def _model_name(self):
        return "fake-1"


def _pregunta():
    return Question(id="q1", type="choice", prompt="decide", criteria=["zeta", "alpha", "mida"])


def test_chat_adapter_lista_posicional():
    ad = _FakeChat('{"probabilities": [0.5, 0.25, 0.25]}')
    d = ad.decide(DecisionRequest(state={"x": 1}, question=_pregunta(), backend="fake"))
    assert list(d.probabilities) == ["zeta", "alpha", "mida"]
    assert abs(sum(d.probabilities.values()) - 1.0) < 1e-9
    assert d.trace.criteria_order == ["zeta", "alpha", "mida"]


def test_chat_adapter_dict_por_nombre_reordena():
    ad = _FakeChat('{"alpha": 1, "zeta": 3, "mida": 0}')
    d = ad.decide(DecisionRequest(state={}, question=_pregunta(), backend="fake"))
    assert list(d.probabilities) == ["zeta", "alpha", "mida"]
    assert d.probabilities["zeta"] == 0.75


def test_chat_adapter_prosa_fallback():
    ad = _FakeChat("yo diria 0.6, 0.3, 0.1 mas o menos")
    d = ad.decide(DecisionRequest(state={}, question=_pregunta(), backend="fake"))
    assert d.probabilities["zeta"] == 0.6


def test_chat_adapter_incompatible_rompe_el_contrato():
    ad = _FakeChat("no se")
    with pytest.raises(Exception):
        ad.decide(DecisionRequest(state={}, question=_pregunta(), backend="fake"))


def test_chat_adapter_noul_devuelve_accion():
    q = Question(id="n1", type="noul", prompt="que hago", criteria=["aislar", "ignorar"])
    ad = _FakeChat('{"probabilities": [0.8, 0.2]}')
    d = ad.decide(DecisionRequest(state={}, question=q, backend="fake"))
    assert d.action == "aislar" and d.text


# ------------------------------------------------------------ config del traductor

def test_chat_config_guardado_desde_la_ui(client):
    r = client.put("/v1/chat/config", json={"base_url": "http://127.0.0.1:8080/v1",
                                            "model": "mini", "timeout": 60})
    assert r.status_code == 200
    cfg = client.get("/v1/chat/config").json()["config"]
    assert cfg["base_url"] == "http://127.0.0.1:8080"
    assert cfg["model"] == "mini"
    assert cfg["url"] == "http://127.0.0.1:8080/v1/chat/completions"


def test_chat_config_rechaza_url_rara(client):
    r = client.put("/v1/chat/config", json={"base_url": "ftp://127.0.0.1:1"})
    assert r.status_code == 422


def test_questions_usan_la_config(client):
    chat_config.save("http://127.0.0.1:8080", "mini")
    assert questions._chat_url() == "http://127.0.0.1:8080/v1/chat/completions"
    assert questions._model() == "mini"


# ------------------------------------------------------------ /v1/ask

def test_ask_routing_llm_validado(client, monkeypatch):
    monkeypatch.setattr(
        questions,
        "compile_question",
        lambda text, default_type="choice", backends=None: (
            Question(id="q", type="choice", prompt="decide", criteria=["a", "b"]),
            {"backend": "mock", "motivo": "prueba", "fuente": "llm"},
        ),
    )
    r = client.post("/v1/ask", json={"text": "decide algo", "state": {"x": 1}})
    assert r.status_code == 200
    body = r.json()
    assert body["question"]["criteria"] == ["a", "b"]
    assert body["decision"]["probabilities"]
    assert "mock" in body["routing"]["candidatos"]


def test_ask_sugerencia_inexistente_usa_fallback(client, monkeypatch):
    monkeypatch.setattr(
        questions,
        "compile_question",
        lambda text, default_type="choice", backends=None: (
            Question(id="q", type="choice", prompt="decide", criteria=["a", "b"]),
            {"backend": "no-existe", "motivo": "el modelo se colo", "fuente": "llm"},
        ),
    )
    body = client.post("/v1/ask", json={"text": "decide"}).json()
    assert body["routing"]["fuente"] in ("codigo", "fallback")
    assert body["routing"]["backend"] in body["routing"]["candidatos"]


def test_ask_mode_all_compara(client, monkeypatch):
    monkeypatch.setattr(
        questions,
        "compile_question",
        lambda text, default_type="choice", backends=None: (
            Question(id="q", type="score", prompt="nivel", criteria=["bajo", "alto"]),
            {"backend": "mock", "motivo": "prueba", "fuente": "llm"},
        ),
    )
    body = client.post("/v1/ask", json={"text": "nivel de riesgo", "mode": "all"}).json()
    assert len(body["decisions"]) >= 1
    for d in body["decisions"]:
        assert list(d["probabilities"]) == ["bajo", "alto"]
        assert d["expected"] is not None


def test_ask_no_acepta_mode_raro(client):
    r = client.post("/v1/ask", json={"text": "hola", "mode": "todo"})
    assert r.status_code == 422
