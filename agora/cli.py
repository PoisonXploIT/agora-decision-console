"""CLI programable de AGORA.

Subcomandos:

    agora backends                 lista los backends registrados
    agora decide --question ... --criteria a b c [--state JSON] [--backend mock]
    agora compare --question ... --criteria a b c
    agora packs list
    agora packs validate [RUTA|PACKS_DIR]
    agora serve [--host 127.0.0.1] [--port 8800]

La salida es JSON con las probabilidades en orden canonico de criterios
(nunca sort_keys). main() devuelve un entero (0 = ok) para poder invocarse
desde tests sin sys.exit.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from agora_core.contract import serialize  # noqa: F401
from agora_core.schemas import DecisionRequest, Question, QuestionType


def _registry() -> dict[str, Any]:
    from agora_adapters import LayaAdapter, MockAdapter

    reg: dict[str, Any] = {"mock": MockAdapter()}
    laya_url = os.environ.get("AGORA_LAYA_URL", "http://127.0.0.1:8787")
    reg["laya"] = LayaAdapter(base_url=laya_url)
    return reg


def _question_from_args(args: argparse.Namespace) -> Question:
    criteria = list(args.criteria)
    return Question(
        id=args.id or "q-cli",
        type=QuestionType(args.type),
        prompt=args.question,
        criteria=criteria,
    )


def _state_from_arg(state: str | None) -> Any:
    if not state:
        return {}
    try:
        return json.loads(state)
    except json.JSONDecodeError as e:
        raise SystemExit(f"--state no es JSON: {e}") from e


def cmd_backends(_: argparse.Namespace) -> int:
    reg = _registry()
    print(
        serialize(
            {"backends": [reg[n].info().model_dump() for n in reg]}
        )
    )
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    reg = _registry()
    q = _question_from_args(args)
    req = DecisionRequest(
        state=_state_from_arg(args.state), question=q, backend=args.backend
    )
    name = (args.backend or "mock").lower()
    if name not in reg:
        print(f"backend desconocido {name!r}", file=sys.stderr)
        return 3
    d = reg[name].decide(req)
    print(serialize(d.model_dump()))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    reg = _registry()
    q = _question_from_args(args)
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name in reg:
        req = DecisionRequest(
            state=_state_from_arg(args.state), question=q, backend=name
        )
        try:
            d = reg[name].decide(req)
        except Exception as e:  # noqa: BLE001
            errors[name] = str(e)
            continue
        results[name] = d.model_dump()
    print(serialize({"question_id": q.id, "results": results, "errors": errors}))
    return 0 if results else 4


def cmd_packs(args: argparse.Namespace) -> int:
    try:
        from agora_serve.packs import list_packs, validate_pack_file
    except ImportError:
        print("packs no disponibles todavia (F5)", file=sys.stderr)
        return 2

    if args.packs_cmd == "list":
        packs = list_packs()
        print(serialize({"packs": [p.model_dump() for p in packs]}))
        return 0
    if args.packs_cmd == "validate":
        path = args.path
        ok, report = validate_pack_file(path) if path else (True, [])
        print(serialize({"ok": ok, "report": report}))
        return 0 if ok else 1
    return 2


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from agora_serve.app import app  # noqa: F401

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agora", description="Consola de decisiones tipadas")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("backends", help="lista backends").set_defaults(func=cmd_backends)

    for name, func in (("decide", cmd_decide), ("compare", cmd_compare)):
        sp = sub.add_parser(name, help=f"{name} una pregunta")
        sp.add_argument("--question", required=True)
        sp.add_argument("--id", default=None)
        sp.add_argument("--type", default="choice", choices=["choice", "score", "noul"])
        sp.add_argument("--criteria", nargs="+", required=True)
        sp.add_argument("--state", default=None, help="JSON del estado (dato no confiable)")
        if name == "decide":
            sp.add_argument("--backend", default="mock")
        sp.set_defaults(func=func)

    pp = sub.add_parser("packs", help="packs de preguntas")
    psub = pp.add_subparsers(dest="packs_cmd", required=True)
    psub.add_parser("list", help="lista packs").set_defaults(func=cmd_packs)
    pv = psub.add_parser("validate", help="valida un pack")
    pv.add_argument("path", nargs="?")
    pv.set_defaults(func=cmd_packs)

    sp = sub.add_parser("serve", help="arranca el servicio HTTP")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8800)
    sp.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return int(args.func(args))
    except SystemExit as e:  # --help o errores de argparse
        code = e.code
        return 0 if code in (0, None) else 2


if __name__ == "__main__":
    raise SystemExit(main())
