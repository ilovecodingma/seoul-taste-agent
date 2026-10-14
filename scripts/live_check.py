"""Run once when the key arrives:  QLOO_API_KEY=... python scripts/live_check.py
Prints the raw harness envelope for one place recommendation (no key is printed)."""
import json
import sys

sys.path.insert(0, ".")
from app.qloo_client import QlooHarnessClient  # noqa: E402

c = QlooHarnessClient()
env = c.recommend("place", ["Radiohead"], "Seongsu-dong, Seoul", limit=3)
print(json.dumps(env, indent=1, ensure_ascii=False)[:3000])
