#!/usr/bin/env python3
"""Jev Classifier — static page + tiny proxy.

Serves ./index.html and proxies POST /api/systemone to the TypeSafe API.
The API key stays on the server (env var); it is never sent to the browser.
Stdlib only: python3 server.py, then open http://localhost:8000

Why a proxy at all? api.typesafe.ai answers OPTIONS with
"Disallowed CORS origin", so a browser cannot call it directly. This also
keeps the key out of client-side JS.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = os.environ.get("JEV_MODEL", "jev-latest")
PORT = int(os.environ.get("PORT", "8000"))
ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_BODY = 512 * 1024  # 0.5 MB of state+questions is plenty


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):  # quieter, timestamped
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/systemone":
            self._json(404, {"error": "not found"})
            return

        key = os.environ.get("TYPESAFE_API_KEY", "").strip()
        if not key:
            self._json(
                500,
                {"error": "TYPESAFE_API_KEY is not set in the server environment. "
                          "Run: TYPESAFE_API_KEY=... python3 server.py"},
            )
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                self._json(413, {"error": "empty or oversized request body"})
                return
            payload = json.loads(self.rfile.read(length))
            state = payload.get("state")
            questions = payload.get("questions")
            if not isinstance(state, str) or not state.strip():
                self._json(400, {"error": "state must be a non-empty string"})
                return
            if not isinstance(questions, dict) or not questions:
                self._json(400, {"error": "questions must be a non-empty object"})
                return
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": f"bad JSON: {exc}"})
            return

        outbound = {
            "model": payload.get("model") or MODEL,
            "state": state,
            "questions": questions,
        }
        req = urllib.request.Request(
            API_URL,
            data=json.dumps(outbound).encode(),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:2000]
            self._json(exc.code, {"error": f"upstream {exc.code}", "detail": detail})
            return
        except urllib.error.URLError as exc:
            self._json(502, {"error": f"cannot reach TypeSafe: {exc.reason}"})
            return

        try:
            answer = json.loads(body)
        except json.JSONDecodeError:
            self._json(502, {"error": "upstream returned non-JSON"})
            return

        answer["_latency_ms"] = round((time.time() - started) * 1000)
        self._json(status, answer)


def main() -> None:
    if not os.path.exists(os.path.join(ROOT, "index.html")):
        sys.exit("index.html not found next to server.py")
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("! TYPESAFE_API_KEY not set — the page will load, requests will fail.",
              file=sys.stderr)
    print(f"Jev Classifier → http://localhost:{PORT}  (model: {MODEL})", file=sys.stderr)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
