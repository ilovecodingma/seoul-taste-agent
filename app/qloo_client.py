"""Thin Qloo Taste API client. The key is injected (env QLOO_API_KEY), never hard-coded.

Hackathon base URL: https://hackathon.api.qloo.com  (header X-Api-Key, GET + query string).
Response parsing is deliberately tolerant: Qloo wraps lists as {"results": [...]} or
{"results": {"entities": [...]}} depending on endpoint.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("QLOO_BASE_URL", "https://hackathon.api.qloo.com")


class QlooError(RuntimeError):
    pass


def _entities(payload):
    res = payload.get("results", payload) if isinstance(payload, dict) else payload
    if isinstance(res, dict):
        res = res.get("entities", [])
    return res if isinstance(res, list) else []


class QlooClient:
    live = True

    def __init__(self, api_key=None, base_url=BASE_URL, min_interval=0.25, timeout=20):
        self.api_key = api_key or os.environ.get("QLOO_API_KEY", "")
        if not self.api_key:
            raise QlooError("QLOO_API_KEY is not set")
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval  # stay well below the 5 req/s guidance
        self.timeout = timeout
        self._last = 0.0
        self._cache = {}  # private server-side cache (allowed by the event rules)

    def _get(self, path, params):
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self.base_url}{path}?{qs}"
        if url in self._cache:
            return self._cache[url]
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"X-Api-Key": self.api_key, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf8"))
        except urllib.error.HTTPError as e:
            raise QlooError(f"Qloo HTTP {e.code} for {path}") from e
        except urllib.error.URLError as e:
            raise QlooError(f"Qloo unreachable: {e.reason}") from e
        finally:
            self._last = time.time()
        self._cache[url] = data
        return data

    def search(self, query, entity_type=None, take=3):
        """Resolve free text to Qloo entities."""
        p = {"query": query, "take": take}
        if entity_type:
            p["types"] = entity_type
        return _entities(self._get("/search", p))

    def insights(self, entity_type, entity_ids=(), tags=(), location=None, take=5):
        """Taste-based recommendations seeded by entity/tag signals."""
        p = {"filter.type": entity_type, "take": take, "feature.explainability": "true"}
        if entity_ids:
            p["signal.interests.entities"] = ",".join(entity_ids)
        if tags:
            p["signal.interests.tags"] = ",".join(tags)
        if location:
            p["filter.location.query"] = location
        return _entities(self._get("/v2/insights", p))
