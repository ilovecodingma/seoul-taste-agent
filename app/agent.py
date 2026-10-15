"""Seoul Taste Agent: a small tool-using agent loop grounded in Qloo.

plan -> probe each district (`qloo exec recommend`, target_type=place, names resolved by Qloo) ->
rank -> compose a one-day route. Every step is recorded in a trace shown in the UI.
An optional LLM (Anthropic key) parses free text and writes the narrative; without
one, a deterministic parser/template is used so the app never depends on a paid model.
"""
import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

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


PREFERRED_TYPES = ["artist", "movie", "tv_show", "book", "video_game", "brand", "place"]


def _pick_candidate(cands, hint=None):
    """Choose among Qloo's ambiguous candidates: hinted type first, else culture types, then popularity."""
    def rank(c):
        t = (c.get("type") or "").rsplit(":", 1)[-1]
        pref = PREFERRED_TYPES.index(t) if t in PREFERRED_TYPES else len(PREFERRED_TYPES)
        return (0 if hint and c.get("type") == hint else 1, pref, -(c.get("popularity") or 0))
    return min((c for c in cands if c.get("id")), key=rank, default=None)


def _why(expl, names):
    """Qloo explainability -> names of the tastes that drove this place (no raw ids shown)."""
    hits = (expl or {}).get("signal.interests.entities") if isinstance(expl, dict) else None
    out = [names.get(h.get("entity_id")) for h in hits or [] if isinstance(h, dict)]
    return ("Matches your taste for " + ", ".join(x for x in out if x)) if any(out) else None


def _summarize(envelope):
    return [e for e in (envelope.get("results") or []) if isinstance(e, dict)]


def run_agent(text, qloo, llm=None, districts=None):
    trace = []
    tastes = parse_tastes(text, llm)
    seeds = [t["text"] for t in tastes]
    trace.append({"step": "parse_tastes", "output": seeds})
    if not seeds:
        return {"error": "Tell me a few things you love (artists, films, shows, books).", "trace": trace}

    scored, resolved = [], []
    hints = {t["text"]: t.get("type") for t in tastes}
    names = {}  # entity id -> display name, to make explainability readable
    items = list((districts or DISTRICTS).items())

    def add(d, env):
        places = _summarize(env)
        if not places:
            return
        affs = [p["affinity"] for p in places if isinstance(p.get("affinity"), (int, float))] or [0.0]
        scored.append({"district": d, "score": round(sum(affs) / len(affs), 3), "places": [
            {"name": p.get("name"), "id": p.get("entity_id"), "affinity": p.get("affinity"),
             "why": _why(p.get("explainability"), names), "info": (p.get("properties") or {}).get("short_description")
             or (p.get("properties") or {}).get("address")} for p in places]})

    # First district also resolves the names (Qloo's own entity resolution); the rest reuse the ids in parallel.
    d0, loc0 = items[0]
    env = qloo.recommend("place", seeds, filter_location=loc0, limit=4)
    if env.get("status") == "needs_input":
        # Ambiguous names: pick the best-fitting candidate and pin it by id; drop names Qloo cannot match.
        issues = (env.get("resolution") or {}).get("issues", [])
        picked, dropped = {}, []
        for i in issues:
            c = _pick_candidate(i.get("candidates") or [], hints.get(i.get("input")))
            if c:
                picked[i.get("input")] = c
            elif i.get("input"):
                dropped.append(i["input"])
        seeds = [picked[s]["id"] if s in picked else s for s in seeds if s not in dropped]
        if picked:
            trace.append({"step": "qloo.resolve: disambiguated", "output": [
                [k, v.get("name"), v.get("type")] for k, v in picked.items()]})
        if dropped:
            trace.append({"step": "qloo.resolve: dropped unmatched", "output": sorted(dropped)})
        if not seeds:
            return {"error": "Qloo could not match any of those. Try more widely known names.", "trace": trace}
        env = qloo.recommend("place", seeds, filter_location=loc0, limit=4)
        if env.get("status") == "needs_input":
            return {"error": "Qloo could not match those names. Try more widely known ones.", "trace": trace}
    resolved = [{"input": x.get("input"), "name": x.get("name"), "id": x.get("entityId")}
                for x in (env.get("interpretation") or {}).get("signals", [])]
    names = {r["id"]: r["name"] for r in resolved}
    seeds = [r["id"] for r in resolved if r["id"]] or seeds
    trace.append({"step": "qloo.recommend resolved signals", "output": resolved})
    add(d0, env)
    if items[1:]:
        with ThreadPoolExecutor(max_workers=4) as ex:
            envs = list(ex.map(lambda it: qloo.recommend("place", seeds, filter_location=it[1], limit=4), items[1:]))
        for (d, _), e in zip(items[1:], envs):
            add(d, e)
    scored.sort(key=lambda s: -s["score"])
    trace.append({"step": "qloo.recommend(place) per district", "output": [[s["district"], s["score"]] for s in scored]})
    if not scored:
        return {"error": "No places came back for those tastes.", "trace": trace}

    # two stops from the best district, two from the runner-up (single district if only one came back)
    pool, seen = [], set()
    for s in scored[:2]:
        for p in [p for p in s["places"] if p["id"] not in seen][:2]:
            seen.add(p["id"])
            pool.append((s["district"], p))
    route = [{"slot": slot, "district": dist, **p} for slot, (dist, p) in zip(TIME_SLOTS, pool)]
    loves = ", ".join(r["name"] or r["input"] for r in resolved) or ", ".join(seeds)
    summary = f"Because you love {loves}, Qloo's taste graph points to {scored[0]['district']} first."
    if llm:
        try:
            summary = llm.narrate(loves, scored[:3], route) or summary
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
