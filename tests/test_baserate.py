import unittest

from wopr.engine.baserate import (
    M_DEFAULT,
    M_MAX,
    Spec,
    Unit,
    bucket_of,
    coarse,
    eb_strength,
    hit,
    nowcast_bucket,
    rate,
    unit_bucket_years,
)


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
        self.assertEqual(bucket_of(u, 2006, s), "active-1|minor")
        self.assertEqual(bucket_of(u, 2008, s), "recent")
        self.assertEqual(bucket_of(u, 2012, s), "dormant")
        self.assertEqual(bucket_of(u, 2016, s), "cold")
        self.assertEqual(bucket_of(u, 2004, s), "cold")  # never hit before

    def test_episode_age_bands(self):
        u = unit(1, "Africa", 2000, {y: 30 for y in range(2005, 2016)})  # 11-year run
        s = spec(1)
        self.assertEqual(bucket_of(u, 2006, s), "active-1|minor")
        self.assertEqual(bucket_of(u, 2007, s), "active-2-3|minor")
        self.assertEqual(bucket_of(u, 2009, s), "active-4-9|minor")
        self.assertEqual(bucket_of(u, 2016, s), "active-10+|minor")
        self.assertEqual(coarse("active-10+|war"), "active")
        self.assertEqual(coarse("cold+nbr"), "cold")
        self.assertEqual(coarse("dormant"), "dormant")

    def test_war_intensity_band(self):
        u = unit(1, "Africa", 2000, {2005: 5000})
        self.assertEqual(bucket_of(u, 2006, spec(1)), "active-1|war")

    def test_neighbor_flag_on_annual_buckets(self):
        u = unit(1, "Africa", 2000, {})
        s = spec(1)
        nbr = {(1, 2010)}  # a neighbor was at war in 2010
        self.assertEqual(bucket_of(u, 2011, s, nbr), "cold+nbr")
        self.assertEqual(bucket_of(u, 2012, s, nbr), "cold")
        self.assertEqual(bucket_of(u, 2011, s, None), "cold")

    def test_run_broken_by_quiet_year_restarts_age(self):
        u = unit(1, "Africa", 2000, {2005: 30, 2006: 30, 2008: 30})
        s = spec(1)
        self.assertEqual(bucket_of(u, 2009, s), "active-1|minor")  # 2007 broke the run

    def test_unit_bucket_years_counts_transitions(self):
        # hits 2005 and 2006: 2006 entered active-1, 2007 entered active-2-3
        u = unit(1, "Africa", 2000, {2005: 30, 2006: 40})
        self.assertEqual(unit_bucket_years(u, spec(1), "active-1|minor"), (1, 1))
        self.assertEqual(unit_bucket_years(u, spec(1), "active-2-3|minor"), (0, 1))


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
        self.assertEqual(r["bucket"], "active-1|minor")
        self.assertEqual(r["bucket_coarse"], "active")
        self.assertGreater(r["p"], 0.0)
        self.assertLess(r["p"], 1.0)
        self.assertEqual(r["levels"]["self"]["years"], 0)  # 2021 not in period
        self.assertIn(r["headline_level"], ("region", "global"))

    def test_sticky_conflict_beats_cold(self):
        sub = self.substrate()
        p_active = rate(spec(1), sub)["p"]
        p_cold = rate(spec(3), sub)["p"]
        self.assertGreater(p_active, p_cold)

    def test_unobserved_years_do_not_decay_bucket(self):
        # unit hit in the substrate's final year; a question two years out must
        # still see it as `active` (status at the data edge), not `recent`
        sub = self.substrate()
        near = rate(spec(1, as_of=2021), sub)
        far = rate(spec(1, as_of=2022), sub)
        self.assertEqual(near["bucket"], "active-1|minor")
        self.assertEqual(far["bucket"], "active-1|minor")
        self.assertEqual(near["p"], far["p"])
        self.assertTrue(any("past the substrate" in n for n in far["notes"]))

    def test_nowcast_promotes_but_never_demotes_or_leaks(self):
        sub = self.substrate()
        partial = {"year": 2021, "months": 5, "country": {3: {"sb": 40, "ns": 0, "os": 0}}, "dyad": {}}
        sub["partial"] = partial
        s_next = spec(3, as_of=2022)  # question about the year AFTER the partial one
        promoted = rate(s_next, sub)
        self.assertEqual(promoted["bucket"], "active-1|minor")
        self.assertIn("nowcast", promoted)
        self.assertTrue(any("nowcast" in n for n in promoted["notes"]))
        # the partial year's own question must not see its own data
        same_year = rate(spec(3, as_of=2021), sub)
        self.assertEqual(same_year["bucket"], "cold")
        self.assertNotIn("nowcast", same_year)
        # a quiet partial year demotes nothing
        partial["country"][1] = {"sb": 3, "ns": 0, "os": 0}
        still_active = rate(spec(1, as_of=2022), sub)
        self.assertEqual(still_active["bucket"], "active-1|minor")
        self.assertNotIn("nowcast", still_active)

    def test_nowcast_extends_episode_age(self):
        sub = self.substrate()
        sub["partial"] = {"year": 2021, "months": 5, "country": {2: {"sb": 60, "ns": 0, "os": 0}}, "dyad": {}}
        r = rate(spec(2, as_of=2022), sub)  # unit 2 has hit every year 2000–2020
        self.assertEqual(r["bucket"], "active-10+|minor")
        self.assertEqual(nowcast_bucket(sub["country"][2], spec(2, as_of=2022).normalized(2020), sub["partial"])["bucket"], "active-10+|minor")

    def test_unknown_unit_raises(self):
        with self.assertRaises(KeyError):
            rate(spec(99), self.substrate())

    def test_backtest_parity_with_live_engine(self):
        # the walk-forward prior at year Y must equal rate() restricted to <Y
        from wopr.engine.backtest import walk

        sub = self.substrate()
        records = walk("country", "deaths", ("sb",), 25, sub, burn_in=5)
        final = [r for r in records if r["year"] == 2020]
        self.assertTrue(final)
        for r in final:
            live = rate(Spec("country", r["unit"], "deaths", ("sb",), 25, as_of=2020, period=(2000, 2019)), sub)
            self.assertEqual(live["bucket"], r["bucket"])
            self.assertLess(abs(live["p"] - r["p"]), 5e-5, f"unit {r['unit']}: {live['p']} vs {r['p']}")


if __name__ == "__main__":
    unittest.main()
