"""Tests del importador ATT&CK y del gate de validacion (F8).

El fixture tests/data/attack_fixture.json es un bundle STIX minimo con
tecnicas, subtecnicas y un objeto no-tecnica (identity) que debe ser
descartado. La tactica canonica de cada item es la primera de
``x-mitre-tactics`` del bundle: ground truth, no inferida.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import gate  # noqa: E402
import import_attack  # noqa: E402

FIXTURE = ROOT / "tests" / "data" / "attack_fixture.json"


def _bundle() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


EXPECTED_ITEMS = [
    {"id": "T1543", "name": "Create or Preserve Account",
     "tactic": "persistence", "parent": None},
    {"id": "T1543.001", "name": "Create Account: Local Account",
     "tactic": "persistence", "parent": "T1543"},
    {"id": "T1543.002", "name": "Create Account: Domain Account",
     "tactic": "persistence", "parent": "T1543"},
    {"id": "T1078", "name": "Valid Accounts",
     "tactic": "persistence", "parent": None},
    {"id": "T1059", "name": "Command and Scripting Interpreter",
     "tactic": "execution", "parent": None},
    {"id": "T1059.001", "name": "PowerShell",
     "tactic": "execution", "parent": "T1059"},
    {"id": "T1562", "name": "Impair Defenses",
     "tactic": "defense-evasion", "parent": None},
    {"id": "T1068", "name": "Exploitation for Privilege Escalation",
     "tactic": "privilege-escalation", "parent": None},
]


def test_items_del_fixture_en_orden_de_bundle():
    items, _ = import_attack.parse_bundle(_bundle())
    assert items == EXPECTED_ITEMS


def test_tacticas_de_ground_truth_del_bundle():
    _, expected = import_attack.parse_bundle(_bundle())
    assert expected == {
        "persistence", "execution", "defense-evasion", "privilege-escalation"
    }


def test_gate_pasa_en_el_fixture():
    items, expected = import_attack.parse_bundle(_bundle())
    ok, report = gate.run_gate(items, expected_tactics=expected)
    assert ok, report


def test_gate_detecta_ids_duplicados():
    items, _ = import_attack.parse_bundle(_bundle())
    broken = items + [items[0]]
    ok, report = gate.run_gate(broken)
    assert not ok
    assert any("duplicados" in line for line in report)


def test_gate_detecta_padre_faltante():
    items, _ = import_attack.parse_bundle(_bundle())
    # sin T1543, sus subtecnicas quedan huérfanas
    orphaned = [it for it in items if it["id"] != "T1543"]
    ok, report = gate.run_gate(orphaned)
    assert not ok
    assert any("T1543" in line and "padre" in line for line in report)


def test_gate_detecta_tactica_sin_cobertura():
    items, expected = import_attack.parse_bundle(_bundle())
    ok, report = gate.run_gate(items, expected_tactics=expected | {"discovery"})
    assert not ok
    assert any("discovery" in line for line in report)


def test_import_attack_escribe_jsonl_en_orden(tmp_path):
    out = tmp_path / "attack_items.jsonl"
    items = import_attack.import_attack(FIXTURE, out)

    assert [it["id"] for it in items] == [it["id"] for it in EXPECTED_ITEMS]

    raw_lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln]
    assert len(raw_lines) == len(EXPECTED_ITEMS)
    # orden posicional de las claves: id primero, sin reordenar
    first = json.loads(raw_lines[0])
    assert list(first) == ["id", "name", "tactic", "parent"]
    assert raw_lines[0].startswith('{"id": "T1543"')

    from gate import read_items_jsonl
    assert read_items_jsonl(out) == EXPECTED_ITEMS


def test_import_attack_no_escribe_si_el_gate_falla(tmp_path):
    bundle = _bundle()
    # rompo el bundle: subtecnica sin padre presente
    bundle["objects"] = [
        o for o in bundle["objects"]
        if o.get("id") not in ("attack-pattern--T1543", "attack-pattern--T1078")
    ]
    bad = tmp_path / "bundle.json"
    bad.write_text(json.dumps(bundle), encoding="utf-8")
    out = tmp_path / "attack_items.jsonl"

    with pytest.raises(ValueError):
        import_attack.import_attack(bad, out)
    assert not out.exists()


def test_main_cli_ok(tmp_path):
    out = tmp_path / "items.jsonl"
    rc = import_attack.main(["--bundle", str(FIXTURE), "--out", str(out)])
    assert rc == 0
    assert out.is_file()
