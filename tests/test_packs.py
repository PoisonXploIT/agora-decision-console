"""Tests del pack GENERAL y su validador (F5)."""
from __future__ import annotations

import json

from agora.cli import main
from agora_core.contract import serialize
from agora_serve.packs import (
    PACKS_DIR,
    list_packs,
    load_pack,
    validate_pack_file,
)


def test_tres_plantillas_general():
    packs = {p.name: p for p in list_packs()}
    assert {"routing.model", "risk.safe_to_run", "injection.precheck"} <= set(packs)
    for p in packs.values():
        if p.part == "GENERAL":
            assert len(p.questions) >= 1


def test_orden_de_criteria_se_conserva():
    """Lo que esta escrito en el JSON es lo que valida el pack."""
    for path in sorted(PACKS_DIR.rglob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        pack = load_pack(path)
        for rq, qv in zip(raw["questions"], pack.questions):
            assert list(qv.criteria) == list(rq["criteria"]), path


def test_serializacion_no_ordena():
    """serialize() conserva el orden escrito (nada de sort_keys)."""
    for path in sorted(PACKS_DIR.rglob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        pack = load_pack(path)
        s = serialize(pack.model_dump())
        back = json.loads(s)
        for rq, qv in zip(raw["questions"], back["questions"]):
            assert qv["criteria"] == rq["criteria"], path


def test_validador_ok_en_packs_del_repo():
    ok, report = validate_pack_file(PACKS_DIR / "general" / "risk.safe_to_run.json")
    assert ok, report


def test_validador_detecta_criterios_duplicados(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "name": "bad",
                "questions": [
                    {
                        "id": "q1",
                        "type": "choice",
                        "prompt": "p",
                        "criteria": ["a", "b", "a"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ok, report = validate_pack_file(bad)
    assert not ok and report


def test_validador_detecta_score_con_un_nivel(tmp_path):
    bad = tmp_path / "bad2.json"
    bad.write_text(
        json.dumps(
            {
                "name": "bad2",
                "questions": [
                    {
                        "id": "q1",
                        "type": "score",
                        "prompt": "p",
                        "criteria": ["solo"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ok, report = validate_pack_file(bad)
    assert not ok and report


def test_validador_fichero_inexistente():
    ok, report = validate_pack_file("no-existe.json")
    assert not ok and "no existe" in report[0]


def test_cli_packs_list():
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(["packs", "list"])
    assert code == 0
    body = json.loads(buf.getvalue())
    names = [p["name"] for p in body["packs"]]
    assert "routing.model" in names
