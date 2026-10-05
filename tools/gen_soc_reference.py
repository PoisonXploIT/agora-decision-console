"""Genera tests/data/soc_reference.json con MockAdapter (referencia congelada).

Uso: .venv\\Scripts\\python.exe tools/gen_soc_reference.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agora_adapters import MockAdapter
from agora_core.schemas import DecisionRequest
from agora_serve.packs import PACKS_DIR, load_pack

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    m = MockAdapter()
    ref: dict[str, object] = {}
    for name in ("netwatch", "finding"):
        pack = load_pack(PACKS_DIR / "soc" / (name + ".json"))
        for q in pack.questions:
            req = DecisionRequest(state={"ref": "soc"}, question=q)
            ref[q.id] = m.decide(req).model_dump()
    out = ROOT / "tests" / "data" / "soc_reference.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(ref, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"escrito {out} con {len(ref)} decisiones")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
