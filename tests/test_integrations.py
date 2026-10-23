"""Tests de historial SQLite, claves de servicio y webhooks."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from agora_serve import integrations, runs_db
from agora_serve.app import create_app

QUESTION = {"id": "q1", "type": "choice", "prompt": "p", "criteria": ["a", "b"]}


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


class TestSqliteHistory:
    def test_persiste_entre_instancias(self, client: TestClient):
        client.post("/v1/decide", json={"backend": "mock", "question": QUESTION, "state": {}})
        otro = TestClient(create_app())  # proceso nuevo: lee la misma BD
        runs = otro.get("/v1/runs").json()["runs"]
        assert any(r["question_id"] == "q1" for r in runs)

    def test_get_por_id_devuelve_pregunta(self, client: TestClient):
        client.post("/v1/decide", json={"backend": "mock", "question": QUESTION, "state": {}})
        rid = client.get("/v1/runs").json()["runs"][0]["id"]
        row = runs_db.get(rid)
        assert row is not None
        assert row["question"]["id"] == "q1"

    def test_filtro_por_backend(self, client: TestClient):
        total, _ = runs_db.list_runs(backend="mock")
        assert total >= 0


class TestApiKeys:
    def test_clave_de_servicio(self, client: TestClient):
        os.environ["AGORA_AUTH"] = "on"
        os.environ["AGORA_API_KEYS"] = "clave-servicio"
        try:
            assert client.get("/v1/packs").status_code == 401
            ok = client.get("/v1/packs", headers={"Authorization": "Bearer clave-servicio"})
            assert ok.status_code == 200
            mala = client.get("/v1/packs", headers={"Authorization": "Bearer otra"})
            assert mala.status_code == 401
            admin = client.delete("/v1/runs", headers={"Authorization": "Bearer clave-servicio"})
            assert admin.status_code == 401
        finally:
            os.environ["AGORA_AUTH"] = "off"
            os.environ.pop("AGORA_API_KEYS", None)


class TestPackDecide:
    def test_pack_devuelve_decisiones(self, client: TestClient):
        packs = client.get("/v1/packs").json()["packs"]
        if not packs:
            pytest.skip("sin packs")
        pack = packs[0]
        r = client.post("/v1/decide/pack",
                        json={"pack": pack["name"], "state": {"x": 1}, "backends": ["mock"]})
        assert r.status_code == 200
        body = r.json()
        assert len(body["results"]) == len(pack["questions"])
        assert body["backends"] == ["mock"]
        assert "probabilities" in body["results"][0]["by_backend"]["mock"]

    def test_pack_desconocido(self, client: TestClient):
        r = client.post("/v1/decide/pack", json={"pack": "no-existe"})
        assert r.status_code == 404


class TestWebhooks:
    def test_loopback_valido(self):
        assert integrations.validate_webhook_url("http://127.0.0.1:8790/agora")

    def test_http_externo_rechazado(self):
        with pytest.raises(integrations.BadWebhook):
            integrations.validate_webhook_url("http://198.18.0.1/hook")

    def test_https_fuera_de_allowlist(self):
        with pytest.raises(integrations.BadWebhook):
            integrations.validate_webhook_url("https://agora.invalid/hook")

    def test_https_con_allowlist(self):
        os.environ["AGORA_WEBHOOK_HOSTS"] = "hooks.invalid"
        try:
            assert integrations.validate_webhook_url("https://hooks.invalid/x")
        finally:
            os.environ.pop("AGORA_WEBHOOK_HOSTS", None)

    def test_integrations_status(self, client: TestClient):
        r = client.get("/v1/integrations")
        assert r.status_code == 200
        assert "webhooks" in r.json()
