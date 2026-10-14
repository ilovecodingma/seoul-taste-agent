"""Stdlib HTTP server: serves static/ and POST /api/plan. Run: python -m app.server"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .agent import get_llm, run_agent
from .mock import MockQloo
from .qloo_client import QlooError, QlooHarnessClient

STATIC = Path(__file__).resolve().parent.parent / "static"
_hits = {}


def make_qloo():
    if os.environ.get("QLOO_API_KEY") and os.environ.get("FORCE_MOCK") != "1":
        return QlooHarnessClient()
    return MockQloo()


class Handler(BaseHTTPRequestHandler):
    qloo = None
    llm = None

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/status":
            return self._send(200, {"qloo_live": self.qloo.live, "llm": bool(self.llm)})
        f = (STATIC / ("index.html" if self.path in ("/", "") else self.path.lstrip("/"))).resolve()
        if f.is_file() and STATIC in f.parents:
            return self._send(200, f.read_bytes(), "text/html; charset=utf-8")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/plan":
            return self._send(404, {"error": "not found"})
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        now = time.time()
        _hits[ip] = [t for t in _hits.get(ip, []) if now - t < 60] + [now]
        if len(_hits[ip]) > 6:  # protect the monthly Qloo quota
            return self._send(429, {"error": "Too many requests, wait a minute."})
        try:
            n = int(self.headers.get("Content-Length", 0))
            text = str(json.loads(self.rfile.read(min(n, 4000)) or b"{}").get("text", ""))[:600]
        except Exception:
            return self._send(400, {"error": "bad request"})
        try:
            self._send(200, run_agent(text, self.qloo, self.llm))
        except QlooError as e:
            self._send(502, {"error": str(e)[:200]})


def main():
    Handler.qloo, Handler.llm = make_qloo(), get_llm()
    port = int(os.environ.get("PORT", "8080"))
    print(f"serving on :{port} qloo_live={Handler.qloo.live} llm={bool(Handler.llm)}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
