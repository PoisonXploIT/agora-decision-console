#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e2e.py - prueba end-to-end de AGORA contra el servicio en marcha.

Recorre los flujos reales (backends, packs, decidir por tipo, comparar, generar
pregunta desde texto, UI y runs) e imprime PASS/FALLO por caso.

Uso:
    .venv\\Scripts\\python.exe tools\\e2e.py [--base http://127.0.0.1:8800]
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

OK = "PASS"
KO = "FALLO"
RES: list[tuple[str, bool, str]] = []


def _req(base: str, path: str, method: str = "GET", body: dict | None = None, timeout: float = 200):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return getattr(r, "status", 200), r.read()
    except urllib.error.HTTPError as e:  # incluye el cuerpo para diagnosticar
        detalle = ""
        try:
            detalle = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code}: {detalle}") from None


def check(nombre: str, fn) -> None:
    t0 = time.monotonic()
    try:
        detalle = fn()
        RES.append((nombre, True, f"{detalle} ({time.monotonic()-t0:.2f}s)"))
    except Exception as e:  # noqa: BLE001
        RES.append((nombre, False, f"{type(e).__name__}: {str(e)[:160]}"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8800")
    ap.add_argument(
        "--backends", default="mock,laya",
        help="backends de decision a probar (por defecto solo mock,laya: LAYA va en CPU y no molesta)",
    )
    a = ap.parse_args()
    base = a.base.rstrip("/")
    pedidos = [x.strip().lower() for x in a.backends.split(",") if x.strip()]

    def health():
        st, raw = _req(base, "/health", timeout=10)
        d = json.loads(raw)
        assert st == 200 and d.get("ok") is True and "mock" in d.get("backends", [])
        return f"backends={d['backends']}"

    check("servicio /health", health)

    backends: list[str] = []

    def lista_backends():
        st, raw = _req(base, "/backends", timeout=10)
        d = json.loads(raw)
        backends[:] = [b["name"] for b in d["backends"]]
        assert backends, "sin backends"
        return "backends=" + ",".join(backends)

    check("GET /backends", lista_backends)

    def catalogo():
        st, raw = _req(base, "/catalog", timeout=25)
        d = json.loads(raw)
        assert len(d["catalog"]) >= 4
        return ", ".join(f"{c['name']}:{'up' if c['up'] else ('off' if c['up'] is False else 'na')}"
                         for c in d["catalog"])

    check("GET /catalog (estado de servidores)", catalogo)

    packs: dict = {}

    def listar_packs():
        st, raw = _req(base, "/v1/packs", timeout=10)
        d = json.loads(raw)
        for p in d["packs"]:
            packs[p["name"]] = p
        assert len(packs) >= 5
        return "packs=" + ",".join(sorted(packs))

    check("GET /v1/packs", listar_packs)

    def decidir(nombre, q, state=None):
        st, raw = _req(base, "/v1/decide", "POST",
                       {"state": state or {"e2e": True}, "backend": nombre, "question": q})
        d = json.loads(raw)
        probs = d["probabilities"]
        assert abs(sum(probs.values()) - 1.0) < 0.02, f"suma {sum(probs.values())}"
        assert set(probs) == set(q["criteria"]), "criterios alterados"
        assert d["trace"]["criteria_order"] == q["criteria"], "orden canonico roto"
        return f"argmax={max(probs, key=probs.get)} p={max(probs.values()):.2f}"

    q_choice = {"id": "e2e.choice", "type": "choice", "prompt": "clasifica el estado",
                "criteria": ["a", "b", "c"]}
    elegidos = [b for b in pedidos if b in backends]
    assert elegidos, f"ninguno de {pedidos} esta registrado; hay {backends}"
    for b in elegidos:
        check(f"decide choice [{b}]", lambda b=b: decidir(b, q_choice))

    q_score = {"id": "e2e.score", "type": "score", "prompt": "gravedad",
               "criteria": ["nada", "baja", "media", "alta"]}
    q_noul = {"id": "e2e.noul", "type": "noul", "prompt": "requiere accion",
              "criteria": ["si", "no"]}

    for b in [x for x in elegidos if x in ("laya", "eikos-4b")]:
        def _score(b=b):
            st, raw = _req(base, "/v1/decide", "POST",
                           {"state": {"e2e": True}, "backend": b, "question": q_score})
            d = json.loads(raw)
            assert d["expected"] is not None, "sin expected"
            return f"expected={d['expected']:.2f}"

        check(f"decide score [{b}]", _score)

        def _noul(b=b):
            st, raw = _req(base, "/v1/decide", "POST",
                           {"state": {"e2e": True}, "backend": b, "question": q_noul})
            d = json.loads(raw)
            assert d["action"] in q_noul["criteria"], "sin action"
            return f"action={d['action']}"

        check(f"decide noul [{b}]", _noul)

    def comparar():
        nombres = elegidos[:3]
        st, raw = _req(base, "/v1/decide/compare", "POST",
                       {"state": {"e2e": True}, "question": q_choice, "backends": nombres})
        d = json.loads(raw)
        assert d, "respuesta vacia"
        return f"backends={nombres} claves={list(d)[:4]}"

    check("POST /v1/decide/compare", comparar)

    def pack_soc():
        p = packs.get("netwatch") or next(iter(packs.values()))
        q = p["questions"][0]
        qq = {"id": q["id"], "type": q["type"], "prompt": q["prompt"], "criteria": q["criteria"]}
        b = "laya" if "laya" in backends else backends[0]
        return decidir(b, qq, state={"title": "python.exe -> host desconocido", "seen_count": 2})

    check("decide con pregunta de pack (SOC netwatch)", pack_soc)

    def from_text():
        st, raw = _req(base, "/v1/questions/from-text", "POST",
                       {"text": "clasifica un comando bash en seguro, dudoso o peligroso"})
        d = json.loads(raw)
        q = d["question"]
        assert q["type"] in ("choice", "score", "noul") and q["criteria"]
        assert d.get("generado_por", {}).get("model"), "sin 'generado_por'"
        return f"type={q['type']} via={d['generado_por']['model']}"

    check("POST /v1/questions/from-text (LLM de chat)", from_text)

    def ui():
        st, raw = _req(base, "/ui/", timeout=10)
        html = raw.decode("utf-8", "replace")
        assert st == 200 and "AGORA" in html and 'id="decidir"' in html
        return f"{len(html)} bytes"

    check("GET /ui/ (consola)", ui)

    def runs():
        st, raw = _req(base, "/v1/runs", timeout=10)
        d = json.loads(raw)
        return f"runs={d.get('count')}"

    check("GET /v1/runs (historial)", runs)

    print()
    paso = sum(1 for _, ok, _ in RES if ok)
    for nombre, ok, detalle in RES:
        print(f"[{OK if ok else KO}] {nombre:44s} {detalle}")
    print()
    print(f"E2E: {paso}/{len(RES)} en verde")
    return 0 if paso == len(RES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
