import unittest

from wopr.engine import watchfloor
from wopr.engine.baserate import Unit


def country(uid, region, annual):
    u = Unit(uid, f"C{uid}", [region], min(annual, default=2000), max(annual, default=2000))
    u.years = {y: {"acd": 1 if v >= 25 else 0, "sb": v, "ns": 0, "os": 0} for y, v in annual.items()}
    return u


class TestWatchfloor(unittest.TestCase):
    def substrate(self, partial_country):
        units = {
            1: country(1, "Africa", {y: 500 for y in range(2020, 2026)}),  # steady war
            2: country(2, "Africa", {y: 0 for y in range(2020, 2026)}),    # long quiet
        }
        units.update(partial_country)
        return {
            "country": units,
            "dyad": {}, "pair": {}, "last_year": 2025,
            "nbr_active": set(), "neighbors": {}, "regime": {}, "coup_span": None,
            "partial": None,  # set by caller
        }

    def test_onset_flag_for_quiet_country_now_active(self):
        sub = self.substrate({2: country(2, "Africa", {y: 0 for y in range(2020, 2026)})})
        # unit 2 has been quiet for years; 2026 candidate months already cross 25
        sub["partial"] = {"year": 2026, "months": 5, "country": {2: {"sb": 300, "ns": 0, "os": 0}}, "dyad": {}}
        # no ACLED files in test env -> acled key None, fine
        board = watchfloor.compute(sub, acled={})
        u = next(x for x in board["units"] if x["gwno"] == 2)
        self.assertEqual(u["direction"], "onset")
        self.assertGreater(u["annualized"], 25)

    def test_heating_and_cooling(self):
        sub = self.substrate({
            3: country(3, "Africa", {y: 1000 for y in range(2020, 2026)}),   # baseline 1000
            4: country(4, "Africa", {y: 1000 for y in range(2020, 2026)}),
        })
        sub["partial"] = {
            "year": 2026, "months": 6,
            "country": {
                3: {"sb": 1500, "ns": 0, "os": 0},  # 3000/yr pace vs 1000 -> heating
                4: {"sb": 100, "ns": 0, "os": 0},    # 200/yr pace vs 1000 -> cooling
            },
            "dyad": {},
        }
        board = watchfloor.compute(sub, acled={})
        d = {u["gwno"]: u["direction"] for u in board["units"]}
        self.assertEqual(d[3], "heating")
        self.assertEqual(d[4], "cooling")

    def test_steady_units_dropped_and_ranked_by_surprise(self):
        sub = self.substrate({
            5: country(5, "Africa", {y: 1000 for y in range(2020, 2026)}),
        })
        sub["partial"] = {
            "year": 2026, "months": 6,
            "country": {
                1: {"sb": 250, "ns": 0, "os": 0},   # ~500/yr vs 500 baseline -> steady, dropped
                5: {"sb": 5000, "ns": 0, "os": 0},   # huge divergence
            },
            "dyad": {},
        }
        board = watchfloor.compute(sub, acled={})
        gwnos = [u["gwno"] for u in board["units"]]
        self.assertNotIn(1, gwnos)          # steady dropped
        self.assertEqual(board["units"][0]["gwno"], 5)  # biggest surprise first


if __name__ == "__main__":
    unittest.main()
