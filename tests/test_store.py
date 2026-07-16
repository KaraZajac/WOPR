import tempfile
import unittest
from pathlib import Path

from wopr.journal import store


def criteria():
    return {
        "scope": {"kind": "country", "id": 530, "name": "Ethiopia"},
        "types": ["sb"],
        "measure": "deaths",
        "threshold": 25,
        "window": {"start": "2026-01-01", "end": "2026-12-31"},
    }


class TestStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = store.QUESTIONS
        store.QUESTIONS = Path(self._tmp.name)

    def tearDown(self):
        store.QUESTIONS = self._old
        self._tmp.cleanup()

    def test_roundtrip_and_id_allocation(self):
        q1 = store.new_question("Test one", "Will it?", criteria())
        store.save(q1)
        q2 = store.new_question("Test two", "Will it too?", criteria())
        self.assertNotEqual(q1["id"], q2["id"])
        self.assertTrue(q2["id"].endswith("-002"))
        loaded = store.load(q1["id"])
        self.assertEqual(loaded["title"], "Test one")
        self.assertEqual(loaded["criteria"]["scope"]["id"], 530)

    def test_forecast_bounds_and_ordering(self):
        q = store.new_question("T", "?", criteria())
        store.add_forecast(q, 0.4, "hmm")
        with self.assertRaises(SystemExit):
            store.add_forecast(q, 1.0)
        with self.assertRaises(SystemExit):
            store.add_forecast(q, 0.0)
        store.save(q)
        self.assertEqual(store.load(q["id"])["forecasts"][0]["p"], 0.4)

    def test_no_forecasts_after_resolution(self):
        q = store.new_question("T", "?", criteria())
        q["status"] = "resolved"
        with self.assertRaises(SystemExit):
            store.add_forecast(q, 0.5)

    def test_validation_rejects_bad_questions(self):
        q = store.new_question("T", "?", criteria())
        q["criteria"]["threshold"] = 0
        self.assertTrue(store.validate_question(q))
        q2 = store.new_question("T", "?", criteria())
        q2["criteria"]["window"] = {"start": "2026-12-31", "end": "2026-01-01"}
        self.assertTrue(any("window" in e for e in store.validate_question(q2)))
        q3 = store.new_question("T", "?", criteria())
        q3["status"] = "resolved"  # without a resolution block
        self.assertTrue(store.validate_question(q3))

    def test_save_refuses_invalid(self):
        q = store.new_question("T", "?", criteria())
        q["criteria"]["scope"]["kind"] = "planet"
        with self.assertRaises(SystemExit):
            store.save(q)


if __name__ == "__main__":
    unittest.main()
