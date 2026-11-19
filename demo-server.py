#!/usr/bin/env python3
"""Serve demo.html (any file) + /api/systemone proxy. Stdlib only.

    TYPESAFE_API_KEY=... python3 demo-server.py
    # -> http://localhost:8000/demo.html
"""
import json, os, sys, urllib.error, urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = os.environ.get("JEV_MODEL", "jev-latest")
ROOT = os.path.dirname(os.path.abspath(__file__))


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/systemone":
            return self._json(404, {"error": "not found"})
        key = os.environ.get("TYPESAFE_API_KEY", "").strip()
        if not key:
            return self._json(500, {"error": "TYPESAFE_API_KEY not set"})
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        out = {"model": payload.get("model") or MODEL,
               "state": payload["state"], "questions": payload["questions"]}
        req = urllib.request.Request(
            API_URL, data=json.dumps(out).encode(), method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return self._json(r.status, json.loads(r.read()))
        except urllib.error.HTTPError as e:
            return self._json(e.code, {"error": f"upstream {e.code}",
                                       "detail": e.read().decode()[:2000]})
        except urllib.error.URLError as e:
            return self._json(502, {"error": f"cannot reach TypeSafe: {e.reason}"})


print(f"http://localhost:8000/demo.html", file=sys.stderr)
ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", 8000))), H).serve_forever()
