"""Test de carga de la UI single-page (F7).

La UI se sirve desde el propio FastAPI en /ui (StaticFiles), asi el test de
carga comprueba que los tres ficheros cargan y que el HTML referencia a
app.js y styles.css.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agora_serve.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_ui_index_carga(client):
    r = client.get("/ui/index.html")
    assert r.status_code == 200
    html = r.text
    for marker in ('id="parte"', 'id="pack"', 'id="backend"',
                  'id="estado"', 'id="decidir"', 'id="tarjetas"',
                  'id="traza"'):
        assert marker in html


def test_ui_index_referencia_app_y_css(client):
    html = client.get("/ui/index.html").text
    assert "app.js" in html
    assert "styles.css" in html


def test_ui_parte_general_y_soc(client):
    html = client.get("/ui/index.html").text
    assert 'value="GENERAL"' in html
    assert 'value="SOC"' in html


def test_ui_app_js_carga(client):
    r = client.get("/ui/app.js")
    assert r.status_code == 200
    body = r.text
    assert "decidir" in body
    assert "/v1/decide" in body
    assert "/v1/packs" in body


def test_ui_styles_carga(client):
    r = client.get("/ui/styles.css")
    assert r.status_code == 200
    assert ".tarjeta" in r.text
