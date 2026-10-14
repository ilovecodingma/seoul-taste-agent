"""Seoul Taste Agent: a small tool-using agent loop grounded in Qloo.

plan -> resolve (Qloo /search) -> probe each district (Qloo /v2/insights, place) ->
rank -> compose a one-day route. Every step is recorded in a trace shown in the UI.
An optional LLM (Anthropic key) parses free text and writes the narrative; without
one, a deterministic parser/template is used so the app never depends on a paid model.
"""
import json
import os
import re
import urllib.request

DISTRICTS = {
    "Seongsu": "Seongsu-dong, Seoul", "Hongdae": "Hongdae, Seoul", "Itaewon": "Itaewon, Seoul",
    "Jongno": "Jongno-gu, Seoul", "Gangnam": "Gangnam-gu, Seoul", "Yeonnam": "Yeonnam-dong, Seoul",
    "Euljiro": "Euljiro, Seoul", "Hannam": "Hannam-dong, Seoul",
}
TIME_SLOTS = ["Morning", "Afternoon", "Evening", "Late night"]
TYPE_HINTS = [
    (r"\b(film|movie|cinema)\b", "urn:entity:movie"), (r"\b(series|drama|show)\b", "urn:entity:tv_show"),
    (r"\b(band|singer|album|music|artist)\b", "urn:entity:artist"), (r"\b(book|novel)\b", "urn:entity:book"),
    (r"\b(game)\b", "urn:entity:video_game"), (r"\b(brand)\b", "urn:entity:brand"),
]
STRIP = r"\b(film|movie|cinema|series|drama|show|band|singer|album|music|artist|book|novel|game|brand)\b"


def parse_tastes(text, llm=None):
    """Free text -> list of {"text", "type"}. LLM if available, else punctuation split."""
    if llm:
        try:
            items = llm.extract(text)
            if items:
                return items
        except Exception:
            pass
    out = []
    for p in re.split(r"[,\n;]|\band\b|&", text):
        p = p.strip(" .\"'")
        if len(p) < 2:
            continue
        typ = next((t for rx, t in TYPE_HINTS if re.search(rx, p, re.I)), None)
        p = re.sub(STRIP, "", p, flags=re.I).strip()
        if p:
            out.append({"text": p, "type": typ})
    return out[:6]


def run_agent(text, qloo, llm=None, districts=None):
    trace = []
    tastes = parse_tastes(text, llm)
    trace.append({"step": "parse_tastes", "output": tastes})
    if not tastes:
        return {"error": "Tell me a few things you love (artists, films, shows, books).", "trace": trace}

    resolved = []
    for t in tastes:
        hits = qloo.search(t["text"], t["type"], take=1)
        if hits:
            h = hits[0]
            resolved.append({"input": t["text"], "name": h.get("name", t["text"]), "id": h.get("entity_id") or h.get("id"),
                             "tags": [x.get("name") for x in h.get("tags", []) if isinstance(x, dict)][:5]})
    resolved = [r for r in resolved if r["id"]]
    trace.append({"step": "qloo.search", "output": [{k: r[k] for k in ("input", "name", "id")} for r in resolved]})
    if not resolved:
        return {"error": "Qloo could not match any of those. Try more widely known names.", "trace": trace}
    ids = [r["id"] for r in resolved]

    scored = []
    for d, loc in (districts or DISTRICTS).items():
        places = qloo.insights("urn:entity:place", entity_ids=ids, location=loc, take=4)
        if not places:
            continue
        affs = [(p.get("query") or {}).get("affinity") for p in places]
        affs = [a for a in affs if isinstance(a, (int, float))] or [0.0]
        scored.append({"district": d, "score": round(sum(affs) / len(affs), 3), "places": [
            {"name": p.get("name"), "id": p.get("entity_id"), "affinity": (p.get("query") or {}).get("affinity"),
             "tags": [x.get("name") for x in p.get("tags", []) if isinstance(x, dict)][:3]} for p in places]})
    scored.sort(key=lambda s: -s["score"])
    trace.append({"step": "qloo.insights(place) per district", "output": [[s["district"], s["score"]] for s in scored]})
    if not scored:
        return {"error": "No places came back for those tastes.", "trace": trace}

    pool = [(s["district"], p) for s in scored[:2] for p in s["places"]]
    route = [{"slot": slot, "district": dist, **p} for slot, (dist, p) in zip(TIME_SLOTS, pool)]
    seeds = ", ".join(r["name"] for r in resolved)
    summary = f"Because you love {seeds}, Qloo's taste graph points to {scored[0]['district']} first."
    if llm:
        try:
            summary = llm.narrate(seeds, scored[:3], route) or summary
        except Exception:
            pass
    trace.append({"step": "compose_route", "output": [r["slot"] + ": " + str(r["name"]) for r in route]})
    return {"simulated": not getattr(qloo, "live", True), "seeds": resolved, "districts": scored,
            "route": route, "summary": summary, "trace": trace}


class AnthropicLLM:
    """Optional. Enabled only when ANTHROPIC_API_KEY is set on the server."""

    def __init__(self, key, model=None):
        self.key, self.model = key, model or os.environ.get("LLM_MODEL", "claude-haiku-4-5")

    def _ask(self, system, user):
        body = json.dumps({"model": self.model, "max_tokens": 500, "system": system,
                           "messages": [{"role": "user", "content": user}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", body, {
            "x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["content"][0]["text"]

    def extract(self, text):
        out = self._ask('Return ONLY a JSON list of {"text": name, "type": one of urn:entity:artist|urn:entity:movie|'
                        'urn:entity:tv_show|urn:entity:book|urn:entity:video_game|urn:entity:brand|null} '
                        "for each cultural item the user loves.", text)
        return json.loads(out[out.index("["): out.rindex("]") + 1])[:6]

    def narrate(self, seeds, top, route):
        return self._ask("In 2 sentences, explain why these Seoul districts match the traveller's taste. "
                         "Use only the given data; do not invent facts.", json.dumps({"loves": seeds, "top": top, "route": route}))


def get_llm():
    k = os.environ.get("ANTHROPIC_API_KEY")
    return AnthropicLLM(k) if k else None
