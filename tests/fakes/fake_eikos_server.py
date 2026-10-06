"""Servidor FALSO local de protocolo Eikos (solo tests).

Implementa ``POST /v1/systemone`` (la API compatible TypeSafe que usa de verdad
``serve.py`` de Eikos) y ``GET /health`` en 127.0.0.1 con un puerto efimero.
Lee el cuerpo (``state`` + ``questions``), registra las imagenes opcionales y
responde con el mapa ``answers`` y probabilidades deterministas en el orden
canonico escrito.

Uso desde pytest:

    server = FakeEikosServer().start()
    try:
        ...  # EikosAdapter(base_url=server.url)
    finally:
        server.stop()
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeEikosHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # silencio en tests
        pass

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True, "model": "eikos-4b"})
        else:
            self._json(404, {"error": "no encontrado"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/systemone":
            self._json(404, {"error": "ruta no soportada"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(length).decode("utf-8"))
            questions = req["questions"]
            images = req.get("images") or []
        except Exception as e:  # noqa: BLE001
            self._json(400, {"error": f"peticion no valida: {e}"})
            return

        if isinstance(self.server, ThreadingHTTPServer):
            self.server.last_images = list(images)  # type: ignore[attr-defined]

        answers: dict[str, dict] = {}
        for qid, q in questions.items():
            qtype = str(q.get("type", "choice"))
            crit = q.get("criteria")
            if qtype == "choice":
                names = list(crit) if isinstance(crit, dict) else list(crit or [])
                weights = [1.0 / (i + 1) for i in range(len(names))]
                total = sum(weights) or 1.0
                probs = {n: w / total for n, w in zip(names, weights)}
                answers[qid] = {
                    "type": "choice",
                    "choice": max(probs, key=probs.get) if probs else None,
                    "probabilities": probs,
                    "confidence": max(probs.values()) if probs else 0.0,
                }
            elif qtype == "score":
                levels = list(crit or [])
                weights = [1.0 / (i + 1) for i in range(len(levels))]
                total = sum(weights) or 1.0
                probs = {str(i): w / total for i, w in enumerate(weights)}
                answers[qid] = {
                    "type": "score",
                    "score": 0.0,
                    "legend": {str(i): lv for i, lv in enumerate(levels)},
                    "probabilities": probs,
                    "confidence": max(probs.values()) if probs else 0.0,
                }
            else:  # noul: probabilidad de 'true'
                answers[qid] = {"type": "noul", "noul": 0.6, "confidence": 0.6}

        self._json(200, {
            "model": "eikos-4b",
            "answers": answers,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        })


class FakeEikosServer:
    """Envoltorio del servidor falso; .url es la base_url para el adaptador."""

    def __init__(self) -> None:
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url: str = ""

    def start(self) -> FakeEikosServer:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeEikosHandler)
        self._httpd.last_images = None  # type: ignore[attr-defined]
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def last_images(self) -> list[str] | None:
        if self._httpd is not None:
            return getattr(self._httpd, "last_images", None)
        return None

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


if __name__ == "__main__":  # manual: python fake_eikos_server.py [puerto]
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
    httpd = ThreadingHTTPServer(("127.0.0.1", port), FakeEikosHandler)
    print(f"fake eikos en http://127.0.0.1:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
