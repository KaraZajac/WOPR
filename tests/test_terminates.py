import unittest

from tocsin.engine.baserate import Spec, Unit, bucket_of, hit, rate


def dyad(uid, years_active):
    """years_active: {year: intensity}"""
    u = Unit(uid, f"D{uid}", ["Asia"], min(years_active), max(years_active))
    u.years = {y: {"acd": v, "sb": v * 500} for y, v in years_active.items()}
    return u


def tspec(uid, as_of=0, period=()):
    return Spec("dyad", uid, "terminates", (), 25, as_of, period)


class TestTerminatesMeasure(unittest.TestCase):
    def setUp(self):
        # episode 2005–2008, then quiet
        self.u = dyad(1, {2005: 1, 2006: 2, 2007: 1, 2008: 1})
        self.s = tspec(1, as_of=2019, period=(2000, 2018))

    def test_hit_semantics(self):
        self.assertFalse(hit(self.u, 2006, self.s))  # active, continues
        self.assertTrue(hit(self.u, 2008, self.s))  # final active year
        self.assertIsNone(hit(self.u, 2010, self.s))  # not at risk when quiet
        self.assertIsNone(hit(self.u, 2003, self.s))  # not yet begun

    def test_bucket_comes_from_activity_twin(self):
        # entering 2008 the episode is in year 3 of a run whose latest year
        # (2007) was minor intensity
        self.assertEqual(bucket_of(self.u, 2008, self.s), "active-2-3|minor")
        # entering 2007, last year (2006) was war intensity
        self.assertEqual(bucket_of(self.u, 2007, self.s), "active-2-3|war")

    def test_rate_prices_termination(self):
        sub = {
            "dyad": {
                1: dyad(1, {2005: 1, 2006: 1, 2007: 1, 2008: 1}),
                2: dyad(2, {2010: 1}),           # one-and-done episode
                3: dyad(3, {2012: 1, 2013: 1}),  # two-year episode
                4: dyad(4, {2000: 1}),
            },
            "country": {},
            "pair": {},
            "last_year": 2018,
            "partial": None,
        }
        r = rate(tspec(2, as_of=2019), sub)
        self.assertGreater(r["p"], 0.0)
        self.assertLess(r["p"], 1.0)
        self.assertEqual(r["spec"]["measure"], "terminates")

    def test_terminates_is_dyad_only(self):
        sub = {"dyad": {}, "country": {}, "pair": {}, "last_year": 2018, "partial": None}
        with self.assertRaises(ValueError):
            rate(Spec("country", 1, "terminates", (), 25, 2019, (2000, 2018)), sub)

    def test_period_excludes_unobservable_final_year(self):
        s = tspec(1).normalized(2018)
        self.assertEqual(s.period[1], 2017)  # 2018 termination needs 2019 data

    def test_bucket_sees_final_data_year_activity(self):
        # episode 2015–2018 (2018 = last data year): a 2019 termination
        # question must bucket on age 4, not age 3
        u = dyad(1, {2015: 1, 2016: 1, 2017: 1, 2018: 1})
        sub = {"dyad": {1: u, 2: dyad(2, {2000: 1})}, "country": {}, "pair": {}, "last_year": 2018, "partial": None}
        r = rate(tspec(1, as_of=2019), sub)
        self.assertEqual(r["bucket"], "active-4-9|minor")


class TestTerminatesResolution(unittest.TestCase):
    def test_decision_rules(self):
        import datetime
        from unittest import mock
        from tocsin.journal import resolve as R

        rows = [
            {"dyad_id": "9", "year": "2024", "acd_intensity": "1"},
            {"dyad_id": "9", "year": "2025", "acd_intensity": "0"},
        ]

        def fake_open(*a, **k):
            import io
            out = io.StringIO()
            import csv as _csv
            w = _csv.DictWriter(out, fieldnames=["dyad_id", "year", "acd_intensity"])
            w.writeheader()
            for r in rows:
                w.writerow(r)
            out.seek(0)
            return out

        crit = lambda y: {"scope": {"kind": "dyad", "id": 9}, "measure": "terminates", "window": {"start": f"{y}-01-01", "end": f"{y}-12-31"}}
        meta = {"ucdp_release": "26.1", "annual_end": datetime.date(2025, 12, 31)}
        with mock.patch("builtins.open", side_effect=lambda *a, **k: fake_open()):
            res = R.resolve_terminates(crit(2024), meta)
            self.assertEqual(res["outcome"], "yes")  # active 2024, quiet 2025
            self.assertEqual(res["decided_on"], "2025-12-31")
            self.assertFalse(res["provisional"])
            res = R.resolve_terminates(crit(2025), meta)
            self.assertEqual(res["outcome"], "no")  # never active in 2025
            self.assertIsNone(R.resolve_terminates(crit(2026), meta))  # pending data


if __name__ == "__main__":
    unittest.main()
