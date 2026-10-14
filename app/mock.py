"""OFFLINE SIMULATION - synthetic, hand-authored data used only for tests / no-key mode.
It is NOT Qloo data and the UI labels it as simulated."""
import hashlib

THEMES = {
    "indie": ["Seongsu", "Yeonnam"], "jazz": ["Itaewon", "Hannam"], "hip hop": ["Itaewon", "Hongdae"],
    "k-pop": ["Gangnam", "Hongdae"], "film": ["Jongno", "Euljiro"], "coffee": ["Seongsu", "Yeonnam"],
    "art": ["Hannam", "Jongno"], "ramen": ["Hongdae", "Euljiro"], "vintage": ["Euljiro", "Seongsu"],
}
PLACES = {
    "Seongsu": ["Warehouse Gallery Cafe", "Roastery Row Coffee Lab", "Handmade Leather Alley"],
    "Hongdae": ["Busker Street Stage", "Live Club Basement 17", "Late-night Ramen Counter"],
    "Itaewon": ["Vinyl & Jazz Bar", "Global Street Food Lane", "Rooftop Listening Room"],
    "Jongno": ["Hanok Teahouse", "Indie Cinema Hall", "Bukchon Craft Studio"],
    "Gangnam": ["Idol Pop-up Store", "Dance Academy Showcase", "Premium Dessert Atelier"],
    "Yeonnam": ["Book & Wine Bar", "Park-side Brunch Cafe", "Zine Shop"],
    "Euljiro": ["Hidden Print Shop Bar", "Retro Noodle House", "Camera Repair Alley"],
    "Hannam": ["Private Collector Gallery", "Natural Wine Kitchen", "Design Bookstore"],
}


def _h(s):
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


class MockQloo:
    live = False

    def search(self, query, entity_type=None, take=3):
        return [{"name": query.title(), "entity_id": "MOCK-" + hashlib.md5(query.lower().encode()).hexdigest()[:8],
                 "types": [entity_type or "urn:entity:artist"], "tags": [{"name": t} for t in self._themes(query)]}]

    def _themes(self, text):
        t = text.lower()
        out = [k for k in THEMES if k in t]
        return out or [list(THEMES)[_h(t) % len(THEMES)]]

    def insights(self, entity_type, entity_ids=(), tags=(), location=None, take=5):
        district = (location or "Seoul").split(",")[0].replace("-dong", "").replace("-gu", "").strip()
        names = PLACES.get(district, [])
        seed = "".join(entity_ids)
        out = []
        for i, n in enumerate(names[:take]):
            aff = 0.55 + (_h(seed + n) % 400) / 1000
            out.append({"name": n, "entity_id": "MOCK-P" + str(_h(n))[-6:], "query": {"affinity": round(aff, 3)},
                        "tags": [{"name": t} for t in ("cafe", "indie", "nightlife", "art")[i % 4: i % 4 + 2]]})
        return sorted(out, key=lambda e: -e["query"]["affinity"])
