"""Tests del importador NVD y su reuso del gate (F9)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import gate  # noqa: E402
import import_nvd  # noqa: E402

FIXTURE = ROOT / "tests" / "data" / "nvd_fixture.json"


def _feed() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


EXPECTED_ITEMS = [
    {"id": "CVE-2021-44228",
     "name": "In Apache Log4j 2.x, JNDI features in Logger configurations do not properly internalize certain user-controlled values. An attacker who can control logger messages may execute arbitrary code loaded from a remote code repository when message lookups are enabled.",
     "tactic": "CWE-74", "parent": None},
    {"id": "CVE-2019-19781",
     "name": "An improper privilege management vulnerability in the Windows Common Log File System Driver could allow an attacker to elevate privileges to SYSTEM.",
     "tactic": "CWE-269", "parent": None},
    {"id": "CVE-2017-0144",
     "name": "A remote code execution vulnerability exists in how SMBv1 handles specially crafted requests, aka 'EternalBlue'.",
     "tactic": "CWE-254", "parent": None},
    {"id": "CVE-2019-0203",
     "name": "Apache Solr 6.x and 7.x is vulnerable to remote code execution due to an insecure deserialization of user-supplied data in the Velocity template engine.",
     "tactic": "CWE-502", "parent": None},
    {"id": "CVE-2023-46809",
     "name": "A vulnerability in the web interfaces of Cisco IOS XE Software and Cisco Catalyst 9000 Series switches allows an unauthenticated, remote attacker to execute arbitrary code on the affected device.",
     "tactic": "CWE-787", "parent": None},
]


def test_items_del_feed_en_orden():
    items, _ = import_nvd.parse_feed(_feed())
    assert items == EXPECTED_ITEMS


def test_cwes_de_ground_truth_del_feed():
    _, expected = import_nvd.parse_feed(_feed())
    assert expected == {"CWE-74", "CWE-502", "CWE-269", "CWE-254", "CWE-787"}


def test_gate_pasa_en_el_fixture():
    items, expected = import_nvd.parse_feed(_feed())
    ok, report = gate.run_gate(items, expected_tactics=expected)
    assert ok, report


def test_gate_detecta_cve_duplicado():
    items, _ = import_nvd.parse_feed(_feed())
    broken = items + [items[0]]
    ok, report = gate.run_gate(broken)
    assert not ok
    assert any("duplicados" in line for line in report)


def test_import_nvd_escribe_jsonl_en_orden(tmp_path):
    out = tmp_path / "nvd_items.jsonl"
    items = import_nvd.import_nvd(FIXTURE, out)

    assert [it["id"] for it in items] == [it["id"] for it in EXPECTED_ITEMS]

    raw_lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln]
    assert len(raw_lines) == len(EXPECTED_ITEMS)
    first = json.loads(raw_lines[0])
    assert list(first) == ["id", "name", "tactic", "parent"]

    from gate import read_items_jsonl
    assert read_items_jsonl(out) == EXPECTED_ITEMS


def test_import_nvd_no_escribe_si_el_gate_falla(tmp_path):
    feed = _feed()
    # rompo el feed: dos CVEs con el mismo id
    feed["results"]["vulnerabilities"] = [
        feed["results"]["vulnerabilities"][0],
        feed["results"]["vulnerabilities"][0],
    ]
    bad = tmp_path / "feed.json"
    bad.write_text(json.dumps(feed), encoding="utf-8")
    out = tmp_path / "nvd_items.jsonl"

    with pytest.raises(ValueError):
        import_nvd.import_nvd(bad, out)
    assert not out.exists()


def test_main_cli_ok(tmp_path):
    out = tmp_path / "items.jsonl"
    rc = import_nvd.main(["--feed", str(FIXTURE), "--out", str(out)])
    assert rc == 0
    assert out.is_file()
