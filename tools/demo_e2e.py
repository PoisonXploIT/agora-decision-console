#!/usr/bin/env python3
"""demo_e2e.py - ejemplo end-to-end de AGORA con datos reales de SOC.

Recorre el flujo completo y muestra, para cada pregunta de los packs SOC:

  1. el veredicto de LAYAA (local, CPU) y de JEV (cloud), con su probabilidad y confianza;
  2. si coinciden o no (equilibrio);
  3. la forma de la distribucion (pico = decide; plana = duda);
  4. genera el informe PDF del pack con todos los modelos.

Uso: .venv\\Scripts\\python.exe tools\\demo_e2e.py
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8800"

ESTADOS = [
    ("Evento de red cloud-AI",
     {"title": "python.exe -> 140.82.113.21:443", "process": "python.exe",
      "dest_ip": "140.82.113.21", "dest_port": 443,
      "catalog_domain": "api.githubcopilot.com", "seen_count": 2,
      "user_active": "autonomous", "beaconing": False},
     "netwatch"),
    ("Finding de escaneo",
     {"tool": "nmap", "category": "OSINT", "severity": "LOW",
      "title": "Puerto 8080 accesible desde internet",
      "description": "Servidor de desarrollo expuesto en 0.0.0.0:8080 sin autenticacion"},
     "finding"),
]


def req(path, body=None, timeout=200):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method="POST" if data else "GET",
                               headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:  # noqa: F821
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:160]}"}


def decide(backend, question, state):
    d = req("/v1/decide", {"state": state, "backend": backend, "question": question})
    return d


def resumen(d):
    p = d.get("probabilities") or {}
    if not p:
        return "(sin resultado)", 0.0, 0.0
    top = max(p, key=p.get)
    conf = p[top]
    # "pico": cuanto de la masa esta en la opcion ganadora (0.25 = reparto, 0.9 = claro)
    return top, conf, max(p.values())


def main() -> int:
    packs = {p["name"]: p for p in req("/v1/packs")["packs"]}
    backends = [b["name"] for b in req("/backends")["backends"]]
    print(f"backends configurados: {', '.join(backends)}")
    print()

    aciertos = 0
    total = 0
    t_laya = []

    for etiqueta, estado, pack_name in ESTADOS:
        pack = packs.get(pack_name)
        if not pack:
            print(f"(falta el pack {pack_name})")
            continue
        print("=" * 96)
        print(f"CASO: {etiqueta}   (pack {pack_name})")
        print(f"estado: {json.dumps(estado, ensure_ascii=False)[:110]}")
        print("=" * 96)
        print(f"{'pregunta':<22}{'LAYAA (local)':<34}{'JEV (cloud)':<30}{'coincide'}")
        print("-" * 96)
        for q in pack["questions"]:
            qq = {"id": q["id"], "type": q["type"], "prompt": q["prompt"], "criteria": q["criteria"]}
            t0 = time.monotonic()
            dl = decide("laya", qq, estado)
            t_laya.append(time.monotonic() - t0)
            dj = decide("jev", qq, estado) if "jev" in backends else {}
            tl, cl, _ = resumen(dl)
            tj, cj, _ = resumen(dj)
            total += 1
            igual = "si" if tl == tj and tl != "(sin resultado)" else "no"
            if igual == "si":
                aciertos += 1
            print(f"{q['id']:<22}{(tl + f'  p={cl:.2f}'):<34}"
                  f"{(tj + f'  p={cj:.2f}'):<30}{igual}")
        print()

    print("=" * 96)
    print(f"acuerdo LAYAA / JEV en estas preguntas: {aciertos}/{total}")
    if t_laya:
        print(f"latencia LAYAA (local, CPU): {1000*sum(t_laya)/len(t_laya):.0f} ms de media "
              f"(min {1000*min(t_laya):.0f}, max {1000*max(t_laya):.0f})")
    print()

    # --- informe PDF del primer pack ---
    etiqueta, estado, pack_name = ESTADOS[0]
    try:
        pdf_req = urllib.request.Request(
            API + "/v1/report",
            data=json.dumps({
                "title": f"Informe de triaje: {etiqueta}",
                "state": estado,
                "pack": pack_name,
                "backends": [b for b in backends if b != "mock"],
            }).encode(),
            method="POST", headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(pdf_req, timeout=600) as r:
            data = r.read()
        out = Path(__file__).resolve().parent.parent / "runs" / "demo-informe.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"informe PDF generado: {out} ({len(data)} bytes)")
    except Exception as e:  # noqa: BLE001
        print("informe PDF: error", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
