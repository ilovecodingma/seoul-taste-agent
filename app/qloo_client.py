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


class QlooRestClient:
    """Documented hackathon REST route (X-Api-Key, https://hackathon.api.qloo.com): GET /search + GET /v2/insights.
    Same recommend() interface and envelope shape as the harness client. Used where Node is too slow (Render free)."""
    live = True
    PREFER = ["artist", "movie", "tv_show", "book", "author", "video_game", "brand", "place"]

    def __init__(self, api_key=None, base_url=None, timeout=30):
        self.api_key = api_key or os.environ.get("QLOO_API_KEY", "")
        if not self.api_key:
            raise QlooError("QLOO_API_KEY is not set")
        self.base = (base_url or os.environ.get("QLOO_BASE_URL") or HACKATHON_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._cache = {}

    def _get(self, path, params):
        import urllib.error
        import urllib.parse
        import urllib.request
        url = f"{self.base}{path}?{urllib.parse.urlencode(params, doseq=True)}"
        if url in self._cache:
            return self._cache[url]
        req = urllib.request.Request(url, headers={"X-Api-Key": self.api_key, "Accept": "application/json",
                                                "User-Agent": "seoul-taste-agent/1.0 (+https://github.com/ilovecodingma/seoul-taste-agent)"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise QlooError(f"Qloo HTTP {e.code} on {path}: {e.read()[:120].decode('utf8', 'replace')}") from None
        except Exception as e:
            raise QlooError(f"Qloo request failed on {path}: {type(e).__name__}") from None
        self._cache[url] = data
        return data

    def _resolve(self, name):
        if len(name) == 36 and name.count("-") == 4:
            return {"id": name, "name": name, "type": None}
        rs = self._get("/search", {"query": name, "limit": 10}).get("results") or []
        def rank(r):
            t = ((r.get("types") or [""])[0]).rsplit(":", 1)[-1]
            exact = (r.get("name") or "").strip().lower() == name.strip().lower()
            return (0 if exact else 1, self.PREFER.index(t) if t in self.PREFER else 99, -(r.get("popularity") or 0))
        best = min((r for r in rs if r.get("entity_id")), key=rank, default=None)
        if not best:
            return None
        return {"id": best["entity_id"], "name": best.get("name"), "type": (best.get("types") or [None])[0]}

    def recommend(self, target_type, signals, filter_location=None, limit=4):
        sigs, unresolved = [], []
        for s in signals:
            r = self._resolve(s)
            (sigs if r else unresolved).append(r or s)
        if unresolved and not sigs:
            return {"status": "needs_input", "results": [], "resolution": {"issues": [{"input": u} for u in unresolved]}}
        params = {"filter.type": "urn:entity:" + target_type, "signal.interests.entities": ",".join(s["id"] for s in sigs),
                  "feature.explainability": "true", "take": limit}
        if filter_location:
            params["filter.location.query"] = filter_location
        data = self._get("/v2/insights", params)
        ents = (data.get("results") or {}).get("entities") or []
        res = [{"entity_id": e.get("entity_id"), "name": e.get("name"), "affinity": (e.get("query") or {}).get("affinity"),
                "explainability": (e.get("query") or {}).get("explainability"), "properties": e.get("properties")} for e in ents]
        return {"status": "ok" if res else "empty", "results": res, "interpretation": {"signals": [
            {"input": s["id"], "entityId": s["id"], "name": s["name"], "type": s["type"]} for s in sigs]}}
