"""Tests del historial, replay, preview de informe y log."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agora_serve.app import create_app

QUESTION = {
    "id": "q1",
    "type": "choice",
    "prompt": "clasifica el comando",
    "criteria": ["seguro", "peligroso"],
}


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _decide(client: TestClient) -> str:
    r = client.post("/v1/decide", json={"backend": "mock", "question": QUESTION,
                                       "state": {"cmd": "ls"}})
    assert r.status_code == 200
    runs = client.get("/v1/runs").json()["runs"]
    return runs[-1]["id"]


def test_historial_guarda_id_y_pregunta(client: TestClient):
    rid = _decide(client)
    runs = client.get("/v1/runs").json()["runs"]
    row = next(r for r in runs if r["id"] == rid)
    assert row["question"]["id"] == "q1"
    assert row["backend"] == "mock"
    assert "state" in row


def test_borrar_un_run(client: TestClient):
    rid = _decide(client)
    r = client.delete(f"/v1/runs/{rid}")
    assert r.status_code == 200
    ids = [x["id"] for x in client.get("/v1/runs").json()["runs"]]
    assert rid not in ids
    assert client.delete(f"/v1/runs/{rid}").status_code == 404


def test_replay_produce_decision_y_nueva_entrada(client: TestClient):
    rid = _decide(client)
    r = client.post(f"/v1/runs/{rid}/replay", json={})
    assert r.status_code == 200
    assert "probabilities" in r.json()
    runs = client.get("/v1/runs").json()["runs"]
    assert any(x.get("replay_of") == rid for x in runs)


def test_replay_con_backend_desconocido(client: TestClient):
    rid = _decide(client)
    r = client.post(f"/v1/runs/{rid}/replay", json={"backend": "no-existe"})
    assert r.status_code == 404


def test_preview_informe(client: TestClient):
    packs = client.get("/v1/packs").json()["packs"]
    if not packs:
        pytest.skip("sin packs en este entorno")
    pack = packs[0]["name"]
    r = client.post("/v1/report/preview", json={"pack": pack, "backends": ["mock"]})
    assert r.status_code == 200
    body = r.json()
    assert body["question_count"] >= 1
    assert body["backends"] == ["mock"]
    assert body["questions"][0]["id"]


def test_logs_expone_lineas(client: TestClient):
    _decide(client)
    r = client.get("/v1/logs?lines=10")
    assert r.status_code == 200
    assert isinstance(r.json()["lines"], list)
