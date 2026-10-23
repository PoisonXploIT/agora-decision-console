"""Contadores Prometheus minimos para AGORA (sin dependencias).

Expuestos en `GET /metrics` (texto plano, formato de Prometheus). Solo agregados:
backend, resultado y numero de runs. No incluye estado, preguntas ni claves.
"""
from __future__ import annotations

import threading
from collections import Counter

_lock = threading.Lock()
_decisions: Counter[str] = Counter()
_errors: Counter[str] = Counter()
_compares = 0
_packs = 0
_webhook_failures = 0


def decision(backend: str, ok: bool = True) -> None:
    global _decisions
    with _lock:
        _decisions[(backend, "ok" if ok else "error")] += 1


def compare(ok: bool = True) -> None:
    global _compares
    with _lock:
        _compares += 1
        if not ok:
            _errors["compare"] += 1


def pack() -> None:
    global _packs
    with _lock:
        _packs += 1


def error(kind: str) -> None:
    with _lock:
        _errors[kind] += 1


def webhook_failure() -> None:
    global _webhook_failures
    with _lock:
        _webhook_failures += 1


def render(runs_total: int) -> str:
    with _lock:
        decisions = dict(_decisions)
        errors = dict(_errors)
        compares, packs, hooks = _compares, _packs, _webhook_failures
    lines = [
        "# HELP agora_decisions_total Decisiones servidas por backend y resultado.",
        "# TYPE agora_decisions_total counter",
    ]
    for (backend, status), n in sorted(decisions.items()):
        lines.append(f'agora_decisions_total{{backend="{backend}",status="{status}"}} {n}')
    lines += [
        "# HELP agora_compares_total Comparaciones de backends.",
        "# TYPE agora_compares_total counter",
        f"agora_compares_total {compares}",
        "# HELP agora_packs_total Decisiones por pack servidas a integraciones.",
        "# TYPE agora_packs_total counter",
        f"agora_packs_total {packs}",
        "# HELP agora_errors_total Errores por tipo.",
        "# TYPE agora_errors_total counter",
    ]
    for kind, n in sorted(errors.items()):
        lines.append(f'agora_errors_total{{kind="{kind}"}} {n}')
    lines += [
        "# HELP agora_webhook_failures_total Entregas de webhook fallidas.",
        "# TYPE agora_webhook_failures_total counter",
        f"agora_webhook_failures_total {hooks}",
        "# HELP agora_runs_total Decisiones guardadas en SQLite.",
        "# TYPE agora_runs_total gauge",
        f"agora_runs_total {runs_total}",
    ]
    return "\n".join(lines) + "\n"
