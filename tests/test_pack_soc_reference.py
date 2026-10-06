"""Test de referencia congelado del pack SOC (F6).

El fichero tests/data/soc_reference.json contiene las decisiones de
MockAdapter para cada pregunta de los packs SOC, con el estado fijo
{"ref": "soc"}. El test comprueba que:

- los criterios son exactamente los de la hoja de ruta, en ese orden;
- la salida actual de MockAdapter sigue siendo igual a la referencia
  (valores y orden posicional de las claves).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agora_adapters.mock import MockAdapter
from agora_core.schemas import DecisionRequest
from agora_serve.packs import PACKS_DIR, load_pack

ROOT = Path(__file__).resolve().parent.parent
REF_PATH = ROOT / "tests" / "data" / "soc_reference.json"


def _load_ref() -> dict:
    return json.loads(REF_PATH.read_text(encoding="utf-8"))


def test_netwatch_criterios_exactos():
    pack = load_pack(PACKS_DIR / "soc" / "netwatch.json")
    q = {x.id: x for x in pack.questions}

    assert list(q["netwatch.clase"].criteria) == [
        "expected_ai_use",
        "background_exfil_suspect",
        "telemetry_noise",
        "unrelated",
    ]
    assert q["netwatch.clase"].type.value == "choice"
    assert len(q["netwatch.severidad"].criteria) == 4
    assert q["netwatch.severidad"].type.value == "score"
    assert q["netwatch.accion"].type.value == "choice"  # 4 opciones -> choice (noul es si/no)


def test_finding_criterios_exactos():
    pack = load_pack(PACKS_DIR / "soc" / "finding.json")
    q = {x.id: x for x in pack.questions}

    assert list(q["finding.clase"].criteria) == [
        "true_positive",
        "false_positive",
        "noise",
    ]
    assert len(q["finding.confianza"].criteria) == 4
    assert q["finding.accion"].type.value == "choice"  # 3 opciones -> choice (noul es si/no)


@pytest.mark.parametrize("qid", ["netwatch.clase", "netwatch.severidad", "netwatch.accion",
                                "finding.clase", "finding.confianza", "finding.accion"])
def test_mock_coincide_con_referencia_congelada(qid):
    ref = _load_ref()
    assert qid in ref, f"falta la referencia para {qid}"

    packs = [
        load_pack(PACKS_DIR / "soc" / (n + ".json"))
        for n in ("netwatch", "finding")
    ]
    q = next(x for p in packs for x in p.questions if x.id == qid)
    decision = MockAdapter().decide(
        DecisionRequest(state={"ref": "soc"}, question=q)
    )

    actual = decision.model_dump()
    # orden posicional de las claves de probabilidades
    assert list(actual["probabilities"]) == list(ref[qid]["probabilities"])
    # valores exactos (Mock determinista)
    for k, v in ref[qid]["probabilities"].items():
        assert actual["probabilities"][k] == pytest.approx(v)
    assert actual["expected"] == ref[qid]["expected"]
    assert actual["action"] == ref[qid]["action"]
    assert actual["type"] == ref[qid]["type"]
