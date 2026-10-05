"""store.py - persistencia de los backends configurados desde la UI.

Guarda en un JSON del perfil del usuario (fuera del repo publico):

    %USERPROFILE%\\.agora\\backends.json   (o AGORA_CONFIG_DIR)

Formato:

    [{"name","kind","base_url","api_key","model"}, ...]

La clave de un backend cloud (p.ej. JEV) se guarda AQUI, en el perfil del
usuario, nunca en el repositorio. El fichero es de lectura/escritura local.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _dir() -> Path:
    d = os.environ.get("AGORA_CONFIG_DIR")
    base = Path(d) if d else (Path.home() / ".agora")
    return base


def store_path() -> Path:
    return _dir() / "backends.json"


def load() -> list[dict[str, Any]]:
    p = store_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [x for x in data if isinstance(x, dict) and x.get("name")] if isinstance(data, list) else []


def save(items: list[dict[str, Any]]) -> None:
    p = store_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception:
        pass


def upsert(item: dict[str, Any]) -> list[dict[str, Any]]:
    items = load()
    items = [x for x in items if x.get("name") != item.get("name")]
    items.append(item)
    save(items)
    return items


def remove(name: str) -> list[dict[str, Any]]:
    items = load()
    items = [x for x in items if x.get("name") != name]
    save(items)
    return items
