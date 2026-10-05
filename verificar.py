#!/usr/bin/env python3
"""AGORA - comprobador de progreso por fases (sin dependencias).

Comprueba EN DISCO que cada fase ha dejado sus ficheros y, con --test, ejecuta
los tests de esa fase con el python del venv.

Uso:
    py -3 verificar.py            lista el estado de todas las fases
    py -3 verificar.py --test     ademas ejecuta los tests de las fases completas
    py -3 verificar.py --all      sale con codigo 1 si alguna fase no esta completa

El agente redirige la salida a verificar.txt:
    .venv\\Scripts\\python.exe verificar.py > verificar.txt
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
MIN_BYTES = 80  # un fichero mas pequeno que esto es un placeholder, no vale

PHASES: list[dict] = [
    {
        "id": "F0",
        "titulo": "Fundacion: esquemas y contrato de orden",
        "files": [
            "pyproject.toml",
            "agora_core/__init__.py",
            "agora_core/schemas.py",
            "agora_core/contract.py",
            "tests/test_schemas.py",
            "tests/test_contract_order.py",
        ],
        "tests": ["tests/test_schemas.py", "tests/test_contract_order.py"],
    },
    {
        "id": "F1",
        "titulo": "Adaptadores base, Mock y Laya",
        "files": [
            "agora_adapters/__init__.py",
            "agora_adapters/base.py",
            "agora_adapters/mock.py",
            "agora_adapters/laya.py",
            "tests/test_adapters_mock.py",
        ],
        "tests": ["tests/test_adapters_mock.py"],
    },
    {
        "id": "F2",
        "titulo": "Adaptador JEV con servidor falso local",
        "files": [
            "agora_adapters/jev.py",
            "tests/fakes/fake_openai_server.py",
            "tests/test_adapters_jev.py",
        ],
        "tests": ["tests/test_adapters_jev.py"],
    },
    {
        "id": "F3",
        "titulo": "Servicio FastAPI",
        "files": [
            "agora_serve/__init__.py",
            "agora_serve/app.py",
            "tests/test_serve.py",
        ],
        "tests": ["tests/test_serve.py"],
    },
    {
        "id": "F4",
        "titulo": "CLI programable",
        "files": [
            "agora/__init__.py",
            "agora/cli.py",
            "tests/test_cli.py",
        ],
        "tests": ["tests/test_cli.py"],
    },
    {
        "id": "F5",
        "titulo": "Pack GENERAL y validador",
        "files": [
            "packs/general/routing.model.json",
            "packs/general/risk.safe_to_run.json",
            "packs/general/injection.precheck.json",
            "agora_serve/packs.py",
            "tests/test_packs.py",
        ],
        "tests": ["tests/test_packs.py"],
    },
    {
        "id": "F6",
        "titulo": "Pack SOC con criterios exactos y test de referencia",
        "files": [
            "packs/soc/netwatch.json",
            "packs/soc/finding.json",
            "tests/data/soc_reference.json",
            "tests/test_pack_soc_reference.py",
        ],
        "tests": ["tests/test_pack_soc_reference.py"],
    },
    {
        "id": "F7",
        "titulo": "UI minima single-page",
        "files": [
            "agora_ui/index.html",
            "agora_ui/app.js",
            "agora_ui/styles.css",
            "tests/test_ui.py",
        ],
        "tests": ["tests/test_ui.py"],
    },
    {
        "id": "F8",
        "titulo": "Importador ATT&CK con gate de validacion",
        "files": [
            "tools/import_attack.py",
            "tools/gate.py",
            "tests/data/attack_fixture.json",
            "tests/test_import_gate.py",
            "data/soc/attack_items.jsonl",
        ],
        "tests": ["tests/test_import_gate.py"],
    },
    {
        "id": "F9",
        "titulo": "Importador NVD reutilizando el gate",
        "files": [
            "tools/import_nvd.py",
            "data/soc/nvd_items.jsonl",
        ],
        "tests": [],
    },
    {
        "id": "F10",
        "titulo": "Adaptador Eikos y guia de arranque local",
        "files": [
            "agora_adapters/eikos.py",
            "tests/fakes/fake_eikos_server.py",
            "tests/test_adapters_eikos.py",
            "docs/eikos-local.md",
        ],
        "tests": ["tests/test_adapters_eikos.py"],
    },
    {
        "id": "F11",
        "titulo": "Empaquetado: README, licencia y contrato",
        "files": [
            "README.md",
            "LICENSE",
            "docs/contrato-decision.md",
            ".gitignore",
        ],
        "tests": [],
    },
]


def check_files(fase: dict) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for rel in fase["files"]:
        p = ROOT / rel
        if not p.is_file():
            missing.append(f"FALTA {rel}")
        elif p.stat().st_size < MIN_BYTES:
            missing.append(f"VACIO {rel}")
    return (not missing), missing


def run_tests(fase: dict) -> tuple[bool, str]:
    if not fase["tests"]:
        return True, ""
    py = str(VENV_PY) if VENV_PY.is_file() else sys.executable
    cmd = [py, "-m", "pytest", "-q", *fase["tests"]]
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=900)
    except Exception as e:  # noqa: BLE001
        return False, f"error lanzando pytest: {e}"
    tail = (r.stdout or "").strip().splitlines()
    return r.returncode == 0, (tail[-1] if tail else f"exit {r.returncode}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="ejecuta los tests de las fases completas")
    ap.add_argument("--all", action="store_true", help="falla si alguna fase no esta completa")
    a = ap.parse_args()

    completas = 0
    pendientes: list[str] = []
    for fase in PHASES:
        ok, missing = check_files(fase)
        nota = ""
        if ok and a.test:
            tok, detail = run_tests(fase)
            if not tok:
                ok = False
                nota = f"  tests FALLAN: {detail}"
        estado = "PASS" if ok else "PENDIENTE"
        print(f"[{estado}] {fase['id']}  {fase['titulo']}")
        if missing:
            for m in missing:
                print(f"         - {m}")
        if nota:
            print(f"         -{nota}")
        if ok:
            completas += 1
        else:
            pendientes.append(fase["id"])

    total = len(PHASES)
    print()
    print(f"Fases completas: {completas}/{total}")
    if pendientes:
        print("Pendientes: " + ", ".join(pendientes))
    else:
        print("Todas las fases completas.")
    if a.all and pendientes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
