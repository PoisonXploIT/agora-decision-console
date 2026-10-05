"""Importador ATT&CK desde bundle STIX (F8).

Lee un bundle STIX de ATT&CK (objetos ``attack-pattern``), construye items SOC
con la tactica del propio bundle como GROUND TRUTH y valida con el gate:

- ids unicos;
- cada subtecnica tiene al padre presente entre los items;
- cobertura: cada tactica del ground truth es la tactica canonica (la primera
  de ``x-mitre-tactics``) de al menos un item.

El orden de los objetos del bundle se conserva en la salida JSONL (sin
``sort_keys``). Los objetos que no sean tecnicas (identities, relaciones...)
se descartan.

Uso como modulo:

    from import_attack import parse_bundle, import_attack
    items, expected = parse_bundle(bundle)
    items = import_attack("bundle.json", "data/soc/attack_items.jsonl")

Uso en linea:

    python tools/import_attack.py --bundle bundle.json [--out data/soc/attack_items.jsonl]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gate import run_gate, write_items_jsonl

TECHNIQUE_TYPE = "attack-pattern"


def _strip_prefix(raw_id: str) -> str:
    """'attack-pattern--T1543.001' -> 'T1543.001'."""
    return raw_id.split("--", 1)[1] if "--" in raw_id else raw_id


def parse_bundle(bundle: dict) -> tuple[list[dict], set[str]]:
    """Extrae items y tacticas de ground truth de un bundle STIX.

    Devuelve ``(items, expected_tactics)`` donde cada item es::

        {"id": "T1543.001", "name": ..., "tactic": "persistence", "parent": "T1543"}

    ``tactic`` es la primera de ``x-mitre-tactics`` (la canonica del bundle)
    y ``parent`` el id sin prefijo de ``x-mitre-tech-ref[0]`` (None si no es
    subtecnica). El orden de salida es el del bundle.
    """
    objects = bundle.get("objects", []) if isinstance(bundle, dict) else []
    items: list[dict] = []
    expected_tactics: set[str] = set()

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if obj.get("type") != TECHNIQUE_TYPE:
            continue

        raw_id = str(obj.get("id", ""))
        tech_id = _strip_prefix(raw_id)
        tactics = [str(t) for t in (obj.get("x-mitre-tactics") or [])]
        expected_tactics.update(tactics)

        refs = obj.get("x-mitre-tech-ref") or []
        parent = _strip_prefix(str(refs[0])) if refs else None

        items.append(
            {
                "id": tech_id,
                "name": str(obj.get("name", "")),
                "tactic": tactics[0] if tactics else None,
                "parent": parent,
            }
        )

    return items, expected_tactics


def import_attack(bundle_path: Path | str, out_path: Path | str) -> list[dict]:
    """Importa el bundle, valida con el gate y escribe la salida JSONL.

    Lanza ``ValueError`` si el gate no pasa (el fichero de salida no se toca).
    Devuelve la lista de items en orden de bundle.
    """
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    items, expected_tactics = parse_bundle(bundle)

    ok, report = run_gate(
        items, expected_tactics=expected_tactics or None
    )
    if not ok:
        raise ValueError("gate ATT&CK no pasa:\n" + "\n".join(report))

    write_items_jsonl(items, Path(out_path))
    return items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Importa un bundle STIX de ATT&CK")
    ap.add_argument("--bundle", required=True, help="ruta del bundle STIX (json)")
    ap.add_argument(
        "--out",
        default="data/soc/attack_items.jsonl",
        help="salida JSONL (por defecto data/soc/attack_items.jsonl)",
    )
    a = ap.parse_args(argv)

    try:
        items = import_attack(a.bundle, a.out)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1

    print(f"OK: {len(items)} items -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
