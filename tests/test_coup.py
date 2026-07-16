import datetime
import io
import unittest
from unittest import mock

from tocsin.engine.baserate import Spec, Unit, bucket_of, hit, rate


def country(uid, coup_years, span=(1950, 2020)):
    """coup_years: {year: (attempts, successes)}"""
    u = Unit(uid, f"C{uid}", ["Africa"], span[0], span[1])
    u.years = {}
    for y in range(span[0], span[1] + 1):
        att, succ = coup_years.get(y, (0, 0))
        u.years[y] = {"acd": 0, "sb": 0, "ns": 0, "os": 0, "coup": att, "coup_s": succ}
    return u


def cspec(uid, as_of=2021, period=(1950, 2020)):
    return Spec("country", uid, "coup", (), 1, as_of, period)


class TestCoupMeasure(unittest.TestCase):
    def test_hit_and_exposure(self):
        u = country(1, {1990: (2, 1)})
        s = cspec(1)
        self.assertTrue(hit(u, 1990, s))
        self.assertFalse(hit(u, 1991, s))
        u.years[2000].pop("coup")  # a year outside P&T coverage
        self.assertIsNone(hit(u, 2000, s))

    def test_success_is_the_war_band(self):
        succ = country(1, {1990: (1, 1)})
        fail = country(2, {1990: (1, 0)})
        s = cspec(1)
        self.assertEqual(bucket_of(succ, 1991, s), "active-1|war")
        self.assertEqual(bucket_of(fail, 1991, cspec(2)), "active-1|minor")
        self.assertEqual(bucket_of(succ, 1996, s), "dormant")

    def test_coup_trap_prices_higher_than_calm(self):
        # active-bucket coup states that frequently re-coup the next year give
        # the active class a real hit rate; the target enters active-1
        coupers = {
            i: country(i, {y: (1, 0) for y in range(1990, 2016, 2)}, span=(1980, 2020))
            for i in range(1, 8)
        }
        calm = {i: country(i, {}, span=(1980, 2020)) for i in range(8, 14)}
        target = country(99, {2019: (1, 0)}, span=(1980, 2020))  # active-1 entering 2020
        sub = {
            "country": {**coupers, **calm, 99: target},
            "dyad": {}, "pair": {}, "last_year": 2020, "coup_span": (1980, 2020), "partial": None,
        }
        trapped = rate(cspec(99, as_of=2020, period=(1980, 2019)), sub)
        quiet = rate(cspec(8, as_of=2020, period=(1980, 2019)), sub)
        self.assertEqual(trapped["bucket"], "active-1|minor")
        self.assertEqual(quiet["bucket"], "cold")
        self.assertGreater(trapped["p"], quiet["p"])

    def test_coup_requires_country_grain_and_table(self):
        sub = {"country": {}, "dyad": {}, "pair": {}, "last_year": 2020, "coup_span": None, "partial": None}
        with self.assertRaises(ValueError):
            rate(Spec("dyad", 1, "coup", (), 1, 2021, (1950, 2020)), sub)


class TestCoupResolution(unittest.TestCase):
    def test_resolution_rules(self):
        from tocsin.journal import resolve as R

        table = "gwno,year,attempts,successes\n432,2024,1,1\n433,2024,0,0\n"

        def fake_open(*a, **k):
            return io.StringIO(table)

        crit = lambda g, y: {"scope": {"kind": "country", "id": g}, "measure": "coup", "window": {"start": f"{y}-01-01", "end": f"{y}-12-31"}}
        with mock.patch("builtins.open", side_effect=fake_open):
            yes = R.resolve_coup(crit(432, 2024))
            self.assertEqual(yes["outcome"], "yes")
            self.assertEqual(yes["basis"]["attempts"], 1)
            no = R.resolve_coup(crit(433, 2024))
            self.assertEqual(no["outcome"], "no")
            self.assertIsNone(R.resolve_coup(crit(432, 2026)))  # table doesn't cover 2026


if __name__ == "__main__":
    unittest.main()
