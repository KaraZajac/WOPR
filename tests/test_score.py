import math
import unittest

from tocsin.journal import score


def q(outcome="yes", prior=0.3, forecasts=None, decided="2026-06-15", status="resolved"):
    return {
        "id": "2026-001",
        "title": "t",
        "status": status,
        "prior": {"p": prior} if prior is not None else None,
        "forecasts": forecasts or [],
        "resolution": {"outcome": outcome, "decided_on": decided, "provisional": False},
    }


class TestScores(unittest.TestCase):
    def test_brier_known_values(self):
        self.assertAlmostEqual(score.brier(0.7, 1), 0.09)
        self.assertAlmostEqual(score.brier(0.7, 0), 0.49)
        self.assertAlmostEqual(score.brier(0.5, 1), 0.25)

    def test_log_score(self):
        self.assertAlmostEqual(score.log_score(0.5, 1), math.log(0.5))
        self.assertAlmostEqual(score.log_score(0.9, 0), math.log(0.1))

    def test_scored_forecast_is_last_before_decision(self):
        fc = [
            {"t": "2026-01-01T00:00:00Z", "p": 0.2},
            {"t": "2026-06-15T23:00:00Z", "p": 0.4},  # decision day still counts
            {"t": "2026-07-01T00:00:00Z", "p": 0.99},  # after the fact: ignored
        ]
        picked = score.scored_forecast(q(forecasts=fc))
        self.assertEqual(picked["p"], 0.4)

    def test_scored_forecast_none_when_all_late(self):
        fc = [{"t": "2026-07-01T00:00:00Z", "p": 0.99}]
        self.assertIsNone(score.scored_forecast(q(forecasts=fc)))

    def test_aggregate_pairing_and_delta(self):
        rows = score.question_rows(
            [
                q(outcome="yes", prior=0.3, forecasts=[{"t": "2026-01-01T00:00:00Z", "p": 0.8}]),
                q(outcome="no", prior=0.3, forecasts=[{"t": "2026-01-01T00:00:00Z", "p": 0.1}]),
                q(outcome="yes", prior=0.6),  # prior-only: excluded from pairing
            ]
        )
        agg = score.aggregate(rows)
        self.assertEqual(agg["resolved"], 3)
        self.assertEqual(agg["paired"], 2)
        # you: (0.04 + 0.01)/2 = 0.025 ; prior on paired: (0.49 + 0.09)/2 = 0.29
        self.assertAlmostEqual(agg["you"]["brier"], 0.025)
        self.assertAlmostEqual(agg["you_vs_prior"]["brier_delta"], 0.025 - 0.29, places=4)
        self.assertEqual(agg["you_vs_prior"]["you_better_on"], 2)

    def test_open_and_void_excluded(self):
        rows = score.question_rows([q(status="open"), q(status="void")])
        self.assertEqual(rows, [])

    def test_prior_computed_after_decision_excluded(self):
        stale = q()
        stale["prior"] = {"p": 0.3, "computed": "2026-07-01T00:00:00Z"}  # decided 2026-06-15
        fresh = q()
        fresh["prior"] = {"p": 0.3, "computed": "2026-06-01T00:00:00Z"}
        rows = score.question_rows([stale, fresh])
        self.assertIsNone(rows[0]["prior_p"])
        self.assertEqual(rows[1]["prior_p"], 0.3)

    def test_calibration_bins(self):
        rows = [
            {"user_p": 0.72, "outcome": 1},
            {"user_p": 0.78, "outcome": 0},
            {"user_p": 0.05, "outcome": 0},
        ]
        bins = score.calibration(rows)
        seventies = next(b for b in bins if b["bin"] == "70–80%")
        self.assertEqual(seventies["n"], 2)
        self.assertAlmostEqual(seventies["mean_p"], 0.75)
        self.assertAlmostEqual(seventies["observed"], 0.5)


if __name__ == "__main__":
    unittest.main()
