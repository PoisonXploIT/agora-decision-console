"""Servidor FALSO local de protocolo OpenAI chat completions (solo tests).

Implementa POST /v1/chat/completions y GET /health en 127.0.0.1 con un puerto
efimero. Lee la pregunta del mensaje user (JSON serializado por AGORA) y
responde SOLO un JSON con 'probabilities' deterministas sobre los criterios,
en el orden canonicamente escrito.

Uso desde pytest:

    server = FakeOpenAIServer()
    server.start()
    try:
        ...  # JevAdapter(base_url=server.url)
    finally:
        server.stop()
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOpenAIHandler(BaseHTTPRequestHandler):
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
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "no encontrado"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self._json(404, {"error": "ruta no soportada"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(length).decode("utf-8"))
            user = None
            for m in req.get("messages", []):
                if m.get("role") == "user":
                    user = m.get("content")
            data = json.loads(user)
            criteria = list(data["question"]["criteria"])
        except Exception as e:  # noqa: BLE001
            self._json(400, {"error": f"peticion no valida: {e}"})
            return

        # distribucion determinista: descendente suave sobre el orden escrito.
        weights = [1.0 / (i + 1) for i in range(len(criteria))]
        total = sum(weights)
        probs = {c: w / total for c, w in zip(criteria, weights)}

        content = json.dumps({"probabilities": probs}, ensure_ascii=False)
        self._json(
            200,
            {
                "id": "fake-1",
                "object": "chat.completion",
                "model": req.get("model", "jev"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
            },
        )


class FakeOpenAIServer:
    """Envoltorio del servidor falso; .url es la base_url para el adaptador."""

    def __init__(self) -> None:
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url: str = ""

    def start(self) -> FakeOpenAIServer:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAIHandler)
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


if __name__ == "__main__":  # manual: python fake_openai_server.py [puerto]
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9300
    httpd = ThreadingHTTPServer(("127.0.0.1", port), FakeOpenAIHandler)
    print(f"fake openai en http://127.0.0.1:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
