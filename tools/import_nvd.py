"""Importador NVD reutilizando el gate de validacion (F9).

Lee un feed JSON de NVD 2.0 (``results.vulnerabilities[].cve``) y construye
items SOC con la misma forma que el importador ATT&CK:

- ``id``      : id del CVE (``CVE-YYYY-NNNNN``);
- ``name``    : descripcion en ingles (la primera disponible);
- ``tactic``  : debilidad canonica, la primera de ``weaknesses`` (CWE),
                ground truth del feed;
- ``parent``  : None (los CVE no tienen padre).

El gate valida lo mismo que en ATT&CK: ids unicos, padres presentes y
cobertura: cada CWE del feed es la CWE canonica de al menos un item.
NVD es dominio publico; sin red ni claves.

Uso como modulo:

    from import_nvd import parse_feed, import_nvd
    items = import_nvd("nvd_feed.json", "data/soc/nvd_items.jsonl")

Uso en linea:

    python tools/import_nvd.py --feed nvd_feed.json [--out data/soc/nvd_items.jsonl]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gate import run_gate, write_items_jsonl


def parse_feed(feed: dict) -> tuple[list[dict], set[str]]:
    """Extrae items y CWEs de ground truth de un feed NVD 2.0.

    Devuelve ``(items, expected_weaknesses)`` conservando el orden del feed.
    """
    vulns = (
        feed.get("results", {}).get("vulnerabilities", [])
        if isinstance(feed, dict)
        else []
    )
    items: list[dict] = []
    expected: set[str] = set()

    for entry in vulns:
        cve = entry.get("cve", {}) if isinstance(entry, dict) else {}
        cve_id = str(cve.get("id", ""))
        if not cve_id:
            continue

        weaknesses = [str(w) for w in (cve.get("weaknesses") or [])]
        expected.update(weaknesses)

        descriptions = cve.get("descriptions") or []
        name = next(
            (d.get("value", "") for d in descriptions if d.get("lang") == "en"),
            descriptions[0].get("value", "") if descriptions else "",
        )

        items.append(
            {
                "id": cve_id,
                "name": str(name),
                "tactic": weaknesses[0] if weaknesses else None,
                "parent": None,
            }
        )

    return items, expected


def import_nvd(feed_path: Path | str, out_path: Path | str) -> list[dict]:
    """Importa el feed NVD, valida con el gate y escribe la salida JSONL.

    Lanza ``ValueError`` si el gate no pasa (el fichero de salida no se toca).
    Devuelve la lista de items en orden de feed.
    """
    feed = json.loads(Path(feed_path).read_text(encoding="utf-8"))
    items, expected_weaknesses = parse_feed(feed)

    ok, report = run_gate(items, expected_tactics=expected_weaknesses or None)
    if not ok:
        raise ValueError("gate NVD no pasa:\n" + "\n".join(report))

    write_items_jsonl(items, Path(out_path))
    return items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Importa un feed JSON de NVD 2.0")
    ap.add_argument("--feed", required=True, help="ruta del feed NVD (json)")
    ap.add_argument(
        "--out",
        default="data/soc/nvd_items.jsonl",
        help="salida JSONL (por defecto data/soc/nvd_items.jsonl)",
    )
    a = ap.parse_args(argv)

    try:
        items = import_nvd(a.feed, a.out)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1

    print(f"OK: {len(items)} CVEs -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
