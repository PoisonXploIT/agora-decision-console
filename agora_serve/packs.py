"""Validador de packs de AGORA (F5).

Un pack es un JSON con preguntas tipadas. El validador:

- carga el JSON conservando el orden (json.load no reordena),
- valida cada pregunta contra los esquemas (choice/score/noul),
- comprueba que el orden escrito de `criteria` se conserva tal cual
  (los criterios son posicionales: nunca se ordenan).
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from agora_core.schemas import Question

ROOT = Path(__file__).resolve().parent.parent
PACKS_DIR = ROOT / "packs"


class Pack(BaseModel):
    """Plantilla de preguntas tipadas (GENERAL o SOC)."""

    name: str = Field(min_length=1)
    title: str | None = None
    description: str | None = None
    part: str | None = None  # "GENERAL" | "SOC"
    questions: list[Question] = Field(min_length=1)


def load_pack(path: Path) -> Pack:
    """Carga y valida un pack; el orden de criteria se conserva."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Pack.model_validate(raw)


def list_packs(root: Path | None = None) -> list[Pack]:
    """Todos los packs bajo `packs/` (por defecto el del repo), ordenados por nombre."""
    base = Path(root) if root is not None else PACKS_DIR
    packs: list[Pack] = []
    for p in sorted(base.rglob("*.json")):
        try:
            packs.append(load_pack(p))
        except (OSError, json.JSONDecodeError, ValidationError):
            continue  # un fichero roto no tumba la lista; validate lo reporta
    return packs


def validate_pack_file(path: str | Path) -> tuple[bool, list[str]]:
    """Valida un fichero de pack y devuelve (ok, informe).

    El informe anota cada infraccion encontrada. En particular comprueba
    que el orden de `criteria` del fichero es el mismo que el validado
    (conservacion de orden posicional).
    """
    report: list[str] = []
    p = Path(path)
    if not p.is_file():
        return False, [f"fichero no existe: {p}"]

    try:
        raw_text = p.read_text(encoding="utf-8")
        raw = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as e:
        return False, [f"JSON invalido: {e}"]

    if not isinstance(raw, dict):
        return False, ["el pack debe ser un objeto JSON"]

    # orden escrito en el fichero, pregunta a pregunta (posicional)
    file_order: list[list[str]] = []
    for q in raw.get("questions", []):
        criteria = q.get("criteria") if isinstance(q, dict) else None
        file_order.append(list(criteria) if isinstance(criteria, list) else [])

    try:
        pack = Pack.model_validate(raw)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(x) for x in err.get("loc", []))
            report.append(f"{loc or 'pack'}: {err['msg']}")
        return False, report

    # conservacion de orden: lo validado debe ser igual a lo escrito
    for i, q in enumerate(pack.questions):
        written = file_order[i] if i < len(file_order) else []
        if list(q.criteria) != written:
            report.append(
                f"pregunta {q.id!r}: el orden de criteria no se conserva "
                f"(fichero {written!r}, validado {list(q.criteria)!r})"
            )

    return (not report), report


def validate_packs_dir(root: Path | None = None) -> tuple[bool, list[str]]:
    base = Path(root) if root is not None else PACKS_DIR
    all_ok = True
    report: list[str] = []
    for p in sorted(base.rglob("*.json")):
        ok, rep = validate_pack_file(p)
        if not ok:
            all_ok = False
            report.extend(f"{p.name}: {line}" for line in rep)
    return all_ok, report
