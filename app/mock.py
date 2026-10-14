"""OFFLINE SIMULATION - synthetic, hand-authored data used only for tests / no-key mode.
It is NOT Qloo data and the UI labels it as simulated. It mimics the `qloo exec recommend` envelope."""
import hashlib

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

    def recommend(self, target_type, signals, filter_location=None, limit=4):
        district = (filter_location or "").split(",")[0].replace("-dong", "").replace("-gu", "").strip()
        seed = "|".join(signals)
        res = []
        for n in PLACES.get(district, [])[:limit]:
            res.append({"entity_id": "MOCK-" + str(_h(n))[-6:], "name": n, "type": target_type,
                        "affinity": round(0.55 + (_h(seed + n) % 400) / 1000, 3)})
        res.sort(key=lambda e: -e["affinity"])
        return {"status": "ok", "results": res, "interpretation": {
            "signals": [{"input": s, "name": s.title(), "entityId": "MOCK-" + str(_h(s))[-6:]} for s in signals]}}
