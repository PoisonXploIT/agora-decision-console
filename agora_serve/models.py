"""models.py - arrancar y parar los servidores de modelo locales desde la UI.

Los lanzadores NO viven en el repo publico: se configuran en

    %USERPROFILE%\\.agora\\models.json     (o AGORA_CONFIG_DIR)

con esta forma:

    {
      "laya":     {"starter": "C:\\\\ruta\\\\laya-serve.bat",   "probe": "http://127.0.0.1:8787/health"},
      "eikos-4b": {"starter": "C:\\\\ruta\\\\eikos4b-serve.bat", "probe": "http://127.0.0.1:8901/health"}
    }

Solo se pueden lanzar lanzadores DECLARADOS aqui (nunca una ruta arbitraria
que venga de la peticion). El arranque abre una ventana de consola nueva para
ver los logs, como los servidores de llama.cpp.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

CREATE_NEW_CONSOLE = 0x00000010


def _dir() -> Path:
    d = os.environ.get("AGORA_CONFIG_DIR")
    return Path(d) if d else (Path.home() / ".agora")


def config_path() -> Path:
    return _dir() / "models.json"


def local_models() -> dict[str, Any]:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _probe(url: str, timeout: float = 2.5) -> bool | None:
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= getattr(r, "status", 200) < 500
    except Exception:
        return False


def _port(url: str) -> int | None:
    m = re.search(r":(\d{2,5})(?:/|$)", url or "")
    return int(m.group(1)) if m else None


def status(name: str) -> dict[str, Any]:
    cfg = local_models().get(name) or {}
    starter = cfg.get("starter")
    probe = cfg.get("probe")
    return {
        "name": name,
        "configurado": bool(starter),
        "starter": starter,
        "probe": probe,
        "up": _probe(probe) if probe else None,
    }


def start(name: str) -> dict[str, Any]:
    cfg = local_models().get(name) or {}
    starter = cfg.get("starter")
    if not starter:
        raise RuntimeError(f"sin lanzador configurado para {name!r} (models.json)")
    if not Path(starter).exists():
        raise RuntimeError(f"el lanzador no existe: {starter}")
    if _probe(cfg.get("probe")):
        return {"name": name, "lanzado": False, "msg": "ya estaba levantado", "up": True}
    # os.startfile abre el .bat en su propia consola como proceso INDEPENDIENTE (como doble clic):
    # asi el servidor del modelo NO muere cuando se reinicia el servicio de AGORA.
    try:
        os.startfile(starter)  # type: ignore[attr-defined]  (solo Windows)
    except Exception:  # noqa: BLE001
        subprocess.Popen(["cmd", "/c", starter], creationflags=CREATE_NEW_CONSOLE)
    return {"name": name, "lanzado": True, "starter": starter, "msg": "ventana abierta; mira los logs"}


def stop(name: str) -> dict[str, Any]:
    cfg = local_models().get(name) or {}
    port = _port(cfg.get("probe") or "")
    if not port:
        raise RuntimeError(f"sin puerto conocido para {name!r} (models.json: probe)")
    try:
        res = subprocess.run(["netstat", "-ano"], capture_output=True, timeout=20)
        out = (res.stdout or b"").decode("cp850", "replace")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"no se pudo consultar netstat: {e}") from e
    pids: set[str] = set()
    for line in out.splitlines():
        if f":{port} " in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts:
                pids.add(parts[-1])
    parados = []
    for pid in sorted(pids):
        subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True, text=True)
        parados.append(pid)
    return {"name": name, "puerto": port, "parados": parados}
