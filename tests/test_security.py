"""Tests de la politica de red, auth local, limites y parada segura."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from agora_serve import security
from agora_serve.app import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


class TestBackendUrlPolicy:
    def test_loopback_http_ok(self):
        for u in ("http://127.0.0.1:8787", "http://localhost:8901", "http://[::1]:9000"):
            assert security.validate_backend_url(u)

    def test_http_remoto_rechazado(self):
        for u in ("http://10.0.0.5:8787", "http://example.com", "http://169.254.169.254"):
            with pytest.raises(security.BadBackendUrl):
                security.validate_backend_url(u)

    def test_https_allowlist(self):
        assert security.validate_backend_url("https://api.typesafe.ai")

    def test_https_host_desconocido(self):
        for u in ("https://evil.example", "https://api.typesafe.ai.evil.tld"):
            with pytest.raises(security.BadBackendUrl):
                security.validate_backend_url(u)

    def test_credenciales_y_query(self):
        for u in ("http://user:pass@127.0.0.1:8787", "http://127.0.0.1:8787/x?y=1",
                  "http://127.0.0.1:8787#frag", "ftp://127.0.0.1:8787", ""):
            with pytest.raises(security.BadBackendUrl):
                security.validate_backend_url(u)


class TestApiGuards:
    def test_alta_backend_externo_rechazada(self, client: TestClient):
        r = client.post("/backends", json={"name": "malo", "kind": "http",
                                          "base_url": "http://10.0.0.5:8787"})
        assert r.status_code == 422

    def test_alta_backend_nombre_invalido(self, client: TestClient):
        r = client.post("/backends", json={"name": "../x", "kind": "http",
                                          "base_url": "http://127.0.0.1:8787"})
        assert r.status_code == 422

    def test_state_demasiado_grande(self, client: TestClient):
        big = {"x": "a" * 70_000}
        r = client.post("/v1/decide", json={
            "backend": "mock",
            "question": {"id": "q", "type": "choice", "prompt": "p", "criteria": ["a", "b"]},
            "state": big,
        })
        assert r.status_code == 413

    def test_texto_largo_rechazado(self, client: TestClient):
        r = client.post("/v1/questions/from-text", json={"text": "x" * 5000})
        assert r.status_code == 422

    def test_stop_sin_confirmacion(self, client: TestClient):
        r = client.post("/models/laya/stop", json={})
        assert r.status_code == 428

    def test_cabeceras_de_seguridad(self, client: TestClient):
        r = client.get("/ui/")
        assert r.status_code == 200
        assert "script-src 'self'" in r.headers["content-security-policy"]
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["cache-control"] == "no-store"

    def test_host_no_local_rechazado(self, client: TestClient):
        r = client.get("/health", headers={"host": "rebind.example"})
        assert r.status_code == 403


class TestToken:
    def test_token_obligatorio(self, client: TestClient):
        os.environ["AGORA_AUTH"] = "on"
        try:
            r = client.get("/v1/packs")
            assert r.status_code == 401
            r2 = client.get("/v1/packs", headers={"X-AGORA-Token": "token-de-test"})
            assert r2.status_code == 200
        finally:
            os.environ["AGORA_AUTH"] = "off"
