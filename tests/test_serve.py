"""Tests del servicio FastAPI de AGORA con TestClient y Mock (F3)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agora_serve.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


QUESTION = {
    "id": "q1",
    "type": "choice",
    "prompt": "decide",
    "criteria": ["zeta", "alpha", "mida"],
}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and "mock" in body["backends"]


def test_backends_incluye_mock(client):
    r = client.get("/backends")
    assert r.status_code == 200
    names = [b["name"] for b in r.json()["backends"]]
    assert "mock" in names
    mock = next(b for b in r.json()["backends"] if b["name"] == "mock")
    assert mock["privacy"] == "local" and mock["local"] is True


def test_decide_choice_orden_canonico(client):
    body = {"question": QUESTION, "state": {"a": 1}}
    r = client.post("/v1/decide", json=body)
    assert r.status_code == 200
    d = r.json()
    assert list(d["probabilities"]) == ["zeta", "alpha", "mida"]
    assert sum(d["probabilities"].values()) == pytest.approx(1.0)
    assert d["trace"]["criteria_order"] == ["zeta", "alpha", "mida"]
    assert d["trace"]["backend"] == "mock"


def test_decide_score_y_noul(client):
    s = client.post(
        "/v1/decide",
        json={"question": {**QUESTION, "id": "qs", "type": "score",
                           "criteria": ["bajo", "medio", "alto"]}},
    )
    assert s.status_code == 200
    assert 1.0 <= s.json()["expected"] <= 3.0

    n = client.post(
        "/v1/decide",
        json={"question": {**QUESTION, "id": "qn", "type": "noul",
                           "criteria": ["bloquear", "monitorizar"]}},
    )
    assert n.status_code == 200
    assert n.json()["action"] in ("bloquear", "monitorizar")


def test_decide_backend_desconocido(client):
    r = client.post(
        "/v1/decide",
        json={"question": QUESTION, "state": {}, "backend": "no-existe"},
    )
    assert r.status_code == 404


def test_compare_devuelve_resultados_y_acuerdo(client):
    r = client.post("/v1/decide/compare", json={"question": QUESTION})
    assert r.status_code == 200
    body = r.json()
    assert "mock" in body["results"]
    assert "agreement" in body
    probs = body["results"]["mock"]["probabilities"]
    assert list(probs) == ["zeta", "alpha", "mida"]


def test_packs_lista(client):
    r = client.get("/v1/packs")
    assert r.status_code == 200
    assert isinstance(r.json()["packs"], list)


def test_runs_registra_y_limpia(client):
    client.post("/v1/decide", json={"question": QUESTION, "state": {}})
    r = client.get("/v1/runs")
    assert r.status_code == 200
    assert r.json()["count"] >= 1

    d = client.delete("/v1/runs")
    assert d.status_code == 200 and d.json()["cleared"] >= 1
    assert client.get("/v1/runs").json()["count"] == 0
