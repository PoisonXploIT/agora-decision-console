"""Herramientas MCP de AGORA: esquemas y despacho.

Cada herramienta devuelve texto JSON compacto para que el agente lo parsee sin
depender del transporte.
"""
from __future__ import annotations

import json
from typing import Any

from .client import AgoraClient, AgoraError

TOOLS: list[dict[str, Any]] = [
    {
        "name": "agora_packs",
        "description": "Lista los packs de decisiones disponibles (GENERAL y SOC-SIEM) "
                       "con su nombre, descripcion y numero de preguntas.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "agora_decide",
        "description": "Evalua un pack completo contra un estado y devuelve una decision "
                       "tipada por pregunta (probabilidades, veredicto y latencia).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pack": {"type": "string", "description": "nombre del pack, p.ej. injection.precheck"},
                "state": {"type": "object", "description": "estado a evaluar (JSON)"},
                "backends": {"type": "array", "items": {"type": "string"},
                             "description": "backends a consultar; por defecto los del servicio"},
            },
            "required": ["pack"],
            "additionalProperties": False,
        },
    },
    {
        "name": "agora_compare",
        "description": "Compara una misma pregunta en varios backends y devuelve el "
                       "acuerdo entre ellos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "object", "description": "pregunta tipada (id, type, prompt, criteria)"},
                "state": {"type": "object"},
                "backends": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "agora_history",
        "description": "Devuelve las ultimas decisiones guardadas en el historial SQLite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
                "backend": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "agora_health",
        "description": "Estado del servicio: backends registrados y numero de decisiones guardadas.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def _summarize_pack(result: dict) -> dict:
    """Reduce la respuesta del pack a lo que un agente necesita."""
    out = []
    for row in result.get("results", []):
        by = row.get("by_backend", {})
        cells = {}
        for backend, res in by.items():
            if "error" in res:
                cells[backend] = {"error": res["error"]}
                continue
            probs = res.get("probabilities", {}) or {}
            winner = max(probs, key=probs.get) if probs else None
            cells[backend] = {"verdict": winner, "p": probs.get(winner) if winner else None,
                              "probabilities": probs}
        out.append({"question_id": row.get("question_id"), "prompt": row.get("prompt"),
                    "type": row.get("type"), "backends": cells})
    return {"pack": result.get("pack"), "results": out, "errors": result.get("errors", {})}


def dispatch(client: AgoraClient, name: str, args: dict[str, Any]) -> dict:
    """Ejecuta una herramienta. Devuelve {content, isError}."""
    try:
        if name == "agora_packs":
            packs = client.packs()
            data = [{"name": p.get("name"), "title": p.get("title"),
                     "description": p.get("description"),
                     "questions": len(p.get("questions", [])),
                     "part": p.get("part")} for p in packs]
        elif name == "agora_decide":
            pack = str(args.get("pack") or "").strip()
            if not pack:
                raise AgoraError("falta 'pack'")
            res = client.decide_pack(pack, args.get("state") or {}, args.get("backends"))
            data = _summarize_pack(res)
        elif name == "agora_compare":
            q = args.get("question")
            if not isinstance(q, dict):
                raise AgoraError("falta 'question' (objeto JSON)")
            data = client.compare(q, args.get("state") or {}, args.get("backends"))
        elif name == "agora_history":
            data = client.history(int(args.get("limit") or 20), args.get("backend"))
        elif name == "agora_health":
            h = client.health()
            data = {"health": h, "runs": client.history(1).get("count")}
        else:
            raise AgoraError(f"herramienta desconocida: {name}")
        return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}
    except (AgoraError, ValueError, TypeError) as e:
        return {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}
