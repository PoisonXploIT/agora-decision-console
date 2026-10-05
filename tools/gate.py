"""Gate de validacion de items SOC (ATT&CK y NVD).

Un item es un dict con, como minimo:

    id      : identificador unico (T1078, T1543.001, CVE-2024-1234, ...)
    name    : nombre legible
    tactic  : tactica como GROUND TRUTH (la del bundle, no la inferida)
    parent  : id del padre si es subtecnica/subitem; None en caso contrario

El gate valida tres cosas:

1. ids unicos.
2. cada subitem con `parent` tiene al padre presente entre los items.
3. cobertura: cada tactica del ground truth esta cubierta por al menos
   un item (si se pasa `expected_tactics`).

Uso como modulo:

    from gate import run_gate
    ok, report = run_gate(items, expected_tactics={...})
"""
from __future__ import annotations

import json
from pathlib import Path


def run_gate(
    items: list[dict],
    expected_tactics: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """Valida la lista de items; devuelve (ok, informe)."""
    report: list[str] = []

    ids = [it.get("id") for it in items]
    idset = set(ids)

    # 1) ids unicos y no vacios
    if any(not i for i in ids):
        report.append("hay items sin id")
    dupes = sorted({i for i in ids if ids.count(i) > 1 and i})
    if dupes:
        report.append(f"ids duplicados: {dupes}")

    # 2) padre de subtecnica presente
    for it in items:
        parent = it.get("parent")
        if parent and parent not in idset:
            report.append(
                f"{it.get('id')}: el padre {parent!r} no esta entre los items"
            )

    # 3) cobertura de tacticas (ground truth)
    if expected_tactics is not None:
        covered = {it.get("tactic") for it in items if it.get("tactic")}
        missing = sorted(expected_tactics - covered)
        if missing:
            report.append(f"tacticas sin cobertura: {missing}")

    return (not report), report


def write_items_jsonl(items: list[dict], path: Path) -> None:
    """Escribe items en JSONL conservando el orden de insercion (sin sort_keys)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def read_items_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items
