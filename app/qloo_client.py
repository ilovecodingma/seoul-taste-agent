"""Qloo access through the official harness (`qloo exec`), the event-supported route.

The hackathon key only works on https://hackathon.api.qloo.com. The key is read from the
server environment (QLOO_API_KEY) and is never sent to the browser or committed.
`qloo exec <workflow>` takes one JSON object on stdin and prints one normalized envelope:
  {"status": ok|empty|needs_input|partial|degraded|error, "summary", "results": [...],
   "interpretation", "resolution": {"issues": [...]}, "error": {"code","retryable","recovery"}}
The harness resolves entity names to Qloo IDs itself, so we pass plain names as `signals`.
"""
import json
import os
import shutil
import subprocess
import threading
import time

HACKATHON_BASE_URL = "https://hackathon.api.qloo.com"


class QlooError(RuntimeError):
    pass


class QlooHarnessClient:
    live = True

    def __init__(self, api_key=None, base_url=None, binary=None, min_interval=0.3, timeout=90):
        self.api_key = api_key or os.environ.get("QLOO_API_KEY", "")
        if not self.api_key:
            raise QlooError("QLOO_API_KEY is not set")
        self.binary = binary or os.environ.get("QLOO_BIN") or shutil.which("qloo")
        if not self.binary:
            raise QlooError("`qloo` not found. Install: npm install --global @qloo/qloo-harness (Node 22.19+)")
        base = base_url or os.environ.get("QLOO_BASE_URL") or HACKATHON_BASE_URL
        self.env = {**os.environ, "QLOO_API_KEY": self.api_key, "QLOO_BASE_URL": base, "QLOO_TRUSTED_BASE_URL": base}
        self.min_interval, self.timeout = min_interval, timeout
        self._last = 0.0
        self._lock = threading.Lock()
        self._cache = {}  # private server-side cache (allowed by the event rules)

    def exec(self, operation, payload):
        key = operation + json.dumps(payload, sort_keys=True)
        if key in self._cache:
            return self._cache[key]
        with self._lock:  # space out call starts (thread-safe)
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
        try:
            p = subprocess.run([self.binary, "exec", operation], input=json.dumps(payload), capture_output=True,
                               text=True, encoding="utf8", env=self.env, timeout=self.timeout)
        except subprocess.TimeoutExpired as e:
            raise QlooError("Qloo timed out") from e
        try:
            env = json.loads(p.stdout)
        except ValueError:
            raise QlooError(f"qloo exec {operation} failed (exit {p.returncode})") from None
        if env.get("status") == "error":
            err = env.get("error") or {}
            raise QlooError(f"Qloo {err.get('code', 'ERROR')}: {env.get('summary', '')}"[:200])
        if env.get("status") == "ok":
            self._cache[key] = env
        return env

    def recommend(self, target_type, signals, filter_location=None, limit=4):
        body = {"target_type": target_type, "signals": signals, "limit": limit, "explain": True}
        if filter_location:
            body["filter_location"] = filter_location
        return self.exec("recommend", body)
