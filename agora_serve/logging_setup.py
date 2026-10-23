"""Log rotado de AGORA, sin prompts ni claves.

Escribe en `~/.agora/agora.log` (1 MB x 3). El panel de registro de la UI lee las
ultimas lineas con `GET /v1/logs`.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FMT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def config_dir() -> Path:
    d = os.environ.get("AGORA_CONFIG_DIR")
    return Path(d) if d else (Path.home() / ".agora")


def log_path() -> Path:
    return config_dir() / "agora.log"


def setup_logging(level: int = logging.INFO) -> Path:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("agora")
    log.setLevel(level)
    if not any(isinstance(h, RotatingFileHandler) for h in log.handlers):
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3,
                                      encoding="utf-8")
        handler.setFormatter(logging.Formatter(_FMT))
        log.addHandler(handler)
    return path


def get_logger() -> logging.Logger:
    return logging.getLogger("agora")


def tail(lines: int = 80) -> list[str]:
    p = log_path()
    if not p.exists():
        return []
    try:
        content = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return content[-max(1, min(500, lines)):]
