import unittest

from wopr.engine.baserate import M_DEFAULT, M_MAX, Spec, Unit, bucket_of, eb_strength, hit, rate, unit_bucket_years


def unit(uid, region, first, years):
    """years: {year: sb_deaths}"""
    u = Unit(uid, f"U{uid}", [region], first, max(years) if years else first)
    u.years = {y: {"acd": 0, "sb": v, "ns": 0, "os": 0} for y, v in years.items()}
    return u


def spec(uid, as_of=2021, period=(2000, 2020), threshold=25):
    return Spec("country", uid, "deaths", ("sb",), threshold, as_of, period)


class TestHitAndBuckets(unittest.TestCase):
    def test_hit_threshold(self):
        u = unit(1, "Africa", 2000, {2005: 30, 2006: 10})
        s = spec(1)
        self.assertTrue(hit(u, 2005, s))
        self.assertFalse(hit(u, 2006, s))
        self.assertFalse(hit(u, 2007, s))  # missing row = zero deaths
        self.assertIsNone(hit(u, 1999, s))  # outside period

    def test_bucket_transitions(self):
        u = unit(1, "Africa", 2000, {2005: 30})
        s = spec(1)
        self.assertEqual(bucket_of(u, 2006, s), "active")
        self.assertEqual(bucket_of(u, 2008, s), "recent")
        self.assertEqual(bucket_of(u, 2012, s), "dormant")
        self.assertEqual(bucket_of(u, 2016, s), "cold")
        self.assertEqual(bucket_of(u, 2004, s), "cold")  # never hit before

    def test_unit_bucket_years_counts_transitions(self):
        # hits 2005 and 2006: the year entered "active" and hit again is 2006
        u = unit(1, "Africa", 2000, {2005: 30, 2006: 40})
        k, n = unit_bucket_years(u, spec(1), "active")
        self.assertEqual((k, n), (1, 2))  # 2006 (hit) and 2007 (no) entered active


class TestEB(unittest.TestCase):
    def test_homogeneous_class_pools_hard(self):
        members = [(2, 20)] * 10
        self.assertEqual(eb_strength(members), M_MAX)

    def test_heterogeneous_class_pools_softly(self):
        members = [(0, 20)] * 5 + [(20, 20)] * 5
        m = eb_strength(members)
        self.assertLess(m, 10)

    def test_degenerate_class_uses_default(self):
        self.assertEqual(eb_strength([(1, 10)]), M_DEFAULT)
        self.assertEqual(eb_strength([]), M_DEFAULT)


class TestRate(unittest.TestCase):
    def substrate(self):
        # one chronically violent unit, several quiet ones, one target that
        # was hit last year (active bucket)
        units = {
            1: unit(1, "Africa", 2000, {2020: 100}),  # target: active entering 2021
            2: unit(2, "Africa", 2000, {y: 50 for y in range(2000, 2021)}),
            3: unit(3, "Africa", 2000, {}),
            4: unit(4, "Africa", 2000, {2010: 30}),
            5: unit(5, "Europe", 2000, {}),
        }
        return {"country": units, "dyad": {}, "last_year": 2020}

    def test_rate_shape_and_bounds(self):
        r = rate(spec(1), self.substrate())
        self.assertEqual(r["bucket"], "active")
        self.assertGreater(r["p"], 0.0)
        self.assertLess(r["p"], 1.0)
        self.assertEqual(r["levels"]["self"]["years"], 0)  # 2021 not in period
        self.assertIn(r["headline_level"], ("region", "global"))

    def test_sticky_conflict_beats_cold(self):
        sub = self.substrate()
        p_active = rate(spec(1), sub)["p"]
        p_cold = rate(spec(3), sub)["p"]
        self.assertGreater(p_active, p_cold)

    def test_unknown_unit_raises(self):
        with self.assertRaises(KeyError):
            rate(spec(99), self.substrate())


if __name__ == "__main__":
    unittest.main()
