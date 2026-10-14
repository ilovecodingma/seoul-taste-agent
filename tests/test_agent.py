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
