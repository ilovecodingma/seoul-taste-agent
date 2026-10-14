import unittest

from app.agent import parse_tastes, run_agent
from app.mock import MockQloo


class T(unittest.TestCase):
    def test_parse(self):
        r = parse_tastes("Bill Evans, Parasite film and Radiohead band")
        self.assertEqual([x["text"] for x in r], ["Bill Evans", "Parasite", "Radiohead"])
        self.assertEqual(r[1]["type"], "urn:entity:movie")

    def test_run_mock(self):
        r = run_agent("indie jazz, coffee, vintage cinema", MockQloo())
        self.assertTrue(r["simulated"])
        self.assertEqual(len(r["route"]), 4)
        self.assertGreaterEqual(len(r["districts"]), 2)

    def test_empty(self):
        self.assertIn("error", run_agent("  ", MockQloo()))


if __name__ == "__main__":
    unittest.main()


class FlakyQloo:
    live = True

    def __init__(self):
        self.calls = []

    def recommend(self, target_type, signals, filter_location=None, limit=4):
        self.calls.append(list(signals))
        if "Zzzz" in signals:
            return {"status": "needs_input", "resolution": {"issues": [{"input": "Zzzz"}]}, "results": []}
        return {"status": "ok", "interpretation": {"signals": [{"input": s, "name": s, "entityId": "id" + s} for s in signals]},
                "results": [{"entity_id": "p1", "name": "Cafe", "affinity": 0.8}]}


class T2(unittest.TestCase):
    def test_needs_input_dropped(self):
        q = FlakyQloo()
        r = run_agent("Radiohead, Zzzz", q)
        self.assertNotIn("error", r)
        self.assertEqual(q.calls[-1], ["Radiohead"])

    def test_harness_client_plumbing(self):
        import os, sys, tempfile, json
        from app.qloo_client import QlooHarnessClient
        d = tempfile.mkdtemp()
        fake = os.path.join(d, "fake.py")
        open(fake, "w").write("import sys,json\nb=json.load(sys.stdin)\nprint(json.dumps({'status':'ok','results':[{'name':'X','echo':b}]}))\n")
        cli = QlooHarnessClient(api_key="k", binary=sys.executable)
        cli.binary = sys.executable
        # emulate `qloo exec recommend` as `python fake.py`
        orig = cli.exec

        import subprocess
        real = subprocess.run
        subprocess.run = lambda cmd, **kw: real([sys.executable, fake], **kw)
        try:
            env = cli.recommend("place", ["a"], "Seoul")
        finally:
            subprocess.run = real
        self.assertEqual(env["results"][0]["echo"]["filter_location"], "Seoul")
