"""Receptor de webhooks de AGORA para pruebas locales.

Uso:
    python integrations/webhook_receiver.py --port 8790

Imprime cada evento recibido. No valida nada: es solo una consola de eco para
comprobar que AGORA entrega los eventos configurados en ~/.agora/integrations.json.
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (API de http.server)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            body = {"raw": raw.decode("utf-8", "replace")[:200]}
        print(json.dumps(body, ensure_ascii=False, indent=2), flush=True)
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:  # silencio
        return


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"escuchando webhooks de AGORA en http://127.0.0.1:{args.port}/agora", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
