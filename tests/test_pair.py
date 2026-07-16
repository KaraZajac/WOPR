import unittest

from wopr.engine.baserate import Spec, Unit, hit, rate
from wopr.journal.resolve import match


def pair_unit(pid, region, years):
    """years: {year: acd_level}; exposure = key presence."""
    u = Unit(pid, f"P{pid}", list(region), min(years), max(years))
    u.years = {y: {"acd": v} for y, v in years.items()}
    return u


def pspec(pid, as_of=2021, period=(2000, 2020)):
    return Spec("pair", pid, "acd-active", (), 25, as_of, period)


class TestPairGrain(unittest.TestCase):
    def test_exposure_is_row_presence(self):
        u = pair_unit(1, ["Asia"], {2000: 0, 2001: 1, 2003: 0})  # 2002 not relevant
        s = pspec(1)
        self.assertFalse(hit(u, 2000, s))
        self.assertTrue(hit(u, 2001, s))
        self.assertIsNone(hit(u, 2002, s))  # gap year: no denominator
        self.assertFalse(hit(u, 2003, s))

    def test_rate_on_pair_substrate(self):
        years_quiet = {y: 0 for y in range(2000, 2021)}
        sub = {
            "country": {},
            "dyad": {},
            "pair": {
                1: pair_unit(1, ["Asia"], {**years_quiet, 2019: 1, 2020: 1}),
                2: pair_unit(2, ["Asia"], years_quiet),
                3: pair_unit(3, ["Asia"], years_quiet),
            },
            "last_year": 2020,
            "partial": None,
        }
        r = rate(pspec(1), sub)
        self.assertEqual(r["bucket"], "active-2-3|minor")
        self.assertGreater(r["p"], rate(pspec(2), sub)["p"])

    def test_pair_rejects_deaths_measure(self):
        sub = {"country": {}, "dyad": {}, "pair": {1: pair_unit(1, ["Asia"], {2020: 0})}, "last_year": 2020, "partial": None}
        with self.assertRaises(ValueError):
            rate(Spec("pair", 1, "deaths", ("sb",), 25, 2021, (2000, 2020)), sub)


class TestPairResolution(unittest.TestCase):
    def crit(self, a=101, b=110):
        return {"scope": {"kind": "pair", "id": a * 1000 + b, "a": a, "b": b}, "types": ["sb"], "measure": "deaths", "threshold": 25}

    def ev(self, **kw):
        row = {"type_of_violence": "1", "gwnoa": "101", "gwnob": "110", "country_id": "101",
               "dyad_new_id": "1", "conflict_new_id": "1", "side_a_new_id": "1", "side_b_new_id": "2",
               "dyad_name": "A - B", "side_a": "A", "side_b": "B", "conflict_name": "X"}
        row.update(kw)
        return row

    def test_matches_either_direction_and_coalitions(self):
        self.assertTrue(match(self.ev(), self.crit(), 2026))
        self.assertTrue(match(self.ev(gwnoa="110", gwnob="101"), self.crit(), 2026))
        self.assertTrue(match(self.ev(gwnoa="2, 101", gwnob="110"), self.crit(), 2026))

    def test_rejects_intrastate_and_other_pairs(self):
        self.assertFalse(match(self.ev(type_of_violence="3"), self.crit(), 2026))
        self.assertFalse(match(self.ev(gwnob=""), self.crit(), 2026))
        self.assertFalse(match(self.ev(gwnob="200"), self.crit(), 2026))

    def test_serbia_alias_applies(self):
        crit = {"scope": {"kind": "pair", "id": 340344, "a": 340, "b": 344}, "types": ["sb"], "measure": "deaths", "threshold": 25}
        self.assertTrue(match(self.ev(gwnoa="345", gwnob="344"), crit, 2010))
        self.assertFalse(match(self.ev(gwnoa="345", gwnob="344"), crit, 2000))


if __name__ == "__main__":
    unittest.main()
