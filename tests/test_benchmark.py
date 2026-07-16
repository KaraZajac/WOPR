import unittest

from wopr.engine.rolling import RollingSpec, mi, rate
from wopr.pipeline.benchmark import summarize
from tests.test_rolling import substrate_with


class TestWalkForwardClamp(unittest.TestCase):
    def test_class_end_hides_the_future(self):
        # unit erupts in 1997; a vantage clamped to 1996-12 must not see it
        eruption = {(1997, m): 500 for m in range(1, 13)}
        sub, monthly = substrate_with({1: ("Africa", eruption), 2: ("Africa", {(1990, 1): 0})})
        clamped = rate(
            RollingSpec("country", 1, ("sb",), 25, 1, start=mi(1997, 1), class_end=mi(1996, 12)),
            sub,
            monthly,
        )
        self.assertEqual(clamped["bucket"], "cold")
        self.assertLess(clamped["p"], 0.05)
        unclamped = rate(RollingSpec("country", 1, ("sb",), 25, 1, start=mi(1998, 1)), sub, monthly)
        self.assertTrue(unclamped["bucket"].startswith("active"))
        self.assertGreater(unclamped["p"], clamped["p"])


class TestSummarize(unittest.TestCase):
    def records(self):
        # views sharp, wopr flat, outcome alternates
        out = []
        for i in range(20):
            o = i % 2
            out.append(
                {
                    "run": "r1",
                    "gwno": 1,
                    "month": f"2024-{i % 12 + 1:02d}",
                    "h": i % 12 + 1,
                    "outcome": o,
                    "provisional": False,
                    "views": 0.9 if o else 0.1,
                    "wopr": 0.5,
                    "climatology": 0.5,
                    "persistence": 0.5,
                }
            )
        return out

    def test_ordering_and_head_to_head(self):
        s = summarize(self.records(), {"threshold": 25})
        self.assertLess(s["models"]["views"]["brier"], s["models"]["wopr"]["brier"])
        self.assertAlmostEqual(s["models"]["views"]["brier"], 0.01, places=6)
        self.assertAlmostEqual(s["models"]["wopr"]["brier"], 0.25, places=6)
        self.assertEqual(s["head_to_head"]["wopr_better_on"], 0)
        self.assertEqual(s["head_to_head"]["views_better_on"], 20)
        self.assertEqual(s["n"], 20)
        self.assertIn("h1-3", s["by_horizon"])
        # climatology skill is 0 against itself by construction
        self.assertAlmostEqual(s["models"]["climatology"]["skill_vs_climatology"], 0.0)


if __name__ == "__main__":
    unittest.main()
