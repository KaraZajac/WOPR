import unittest

from wopr.engine.baserate import Spec, Unit, bucket_of
from wopr.engine.rolling import START, RollingSpec, bucket_series, cumsum, mi, rate, window_sum, ym


def monthly_country(per_month: dict, end=(1998, 12)):
    """Build a raw monthly array from {(y, m): sb_deaths}."""
    n = mi(*end) - START + 1
    arr = [None] * n
    for (y, m), v in per_month.items():
        arr[mi(y, m) - START] = {"sb": v, "ns": 0, "os": 0}
    return arr


def substrate_with(units_years, end=(1998, 12)):
    """Annual substrate (exposure/regions) + monthly overlay."""
    sub = {"country": {}, "dyad": {}, "pair": {}, "last_year": end[0], "partial": None}
    monthly = {"country": {}, "dyad": {}, "final_end": mi(*end), "data_end": mi(*end)}
    for uid, (region, per_month) in units_years.items():
        years = sorted({y for (y, _m) in per_month} | set(range(1989, end[0] + 1)))
        u = Unit(uid, f"U{uid}", [region], min(years), max(years))
        u.years = {
            y: {"acd": 0, "sb": sum(v for (yy, _m), v in per_month.items() if yy == y), "ns": 0, "os": 0}
            for y in years
        }
        sub["country"][uid] = u
        monthly["country"][uid] = monthly_country(per_month, end)
    return sub, monthly


STEADY = {(y, m): 10 for y in range(1992, 1996) for m in range(1, 13)}  # 120/yr, 1992–95


class TestPrimitives(unittest.TestCase):
    def test_month_index_roundtrip(self):
        self.assertEqual(ym(mi(2026, 8)), "2026-08")
        self.assertEqual(mi(1989, 1), START)

    def test_window_sum_and_bounds(self):
        C = cumsum({1: monthly_country(STEADY)}, 1, ("sb",), mi(1998, 12))
        self.assertEqual(window_sum(C, mi(1992, 1), 12), 120)
        self.assertEqual(window_sum(C, mi(1991, 7), 12), 60)  # straddles the onset
        self.assertIsNone(window_sum(C, mi(1998, 6), 12))  # runs past data end
        self.assertIsNone(window_sum(C, START - 5, 12))


class TestBuckets(unittest.TestCase):
    def series(self, per_month=STEADY, threshold=25):
        C = cumsum({1: monthly_country(per_month)}, 1, ("sb",), mi(1998, 12))
        return bucket_series(C, RollingSpec("country", 1, ("sb",), threshold, 12, 0))

    def test_lifecycle(self):
        b = self.series()
        self.assertEqual(b[mi(1991, 6)], "cold")  # nothing yet
        self.assertEqual(b[mi(1992, 4)], "active-1")  # trailing year crossed 25
        self.assertEqual(b[mi(1994, 6)], "active-2-3")
        self.assertEqual(b[mi(1996, 6)], "active-4-9")  # run still alive via trailing windows
        self.assertEqual(b[mi(1998, 1)], "recent")  # activity ended 1995
        # gap bands sit 12 under the annual ones (last_R trails activity by ~1y)
        self.assertEqual(b[mi(1998, 12)], "dormant")

    def test_annual_equivalence_at_january(self):
        sub, monthly = substrate_with({1: ("Africa", STEADY)})
        u = sub["country"][1]
        annual = Spec("country", 1, "deaths", ("sb",), 25, 0, (1989, 1998))
        C = cumsum(monthly["country"], 1, ("sb",), monthly["data_end"])
        b = bucket_series(C, RollingSpec("country", 1, ("sb",), 25, 12, 0))
        for year in (1992, 1993, 1995, 1996, 1998):
            self.assertEqual(
                b[mi(year, 1)].split("|")[0],  # suffixes differ by grain (tempo vs intensity)
                bucket_of(u, year, annual).split("|")[0],
                f"January {year} bucket must match the annual engine",
            )
            self.assertEqual(window_sum(C, mi(year - 1, 1), 12), u.years[year - 1]["sb"])

    def test_tempo_bands_split_active(self):
        from wopr.engine.rolling import prefixes

        sustained = {(y, m): 30 for y in (1992, 1993) for m in range(1, 13)}  # 12 hit-months/yr
        spike = {(1992, 6): 400, (1993, 6): 400}  # one hit-month/yr, same activity status
        for per_month, expect in ((sustained, "high"), (spike, "low")):
            C, H = prefixes({1: monthly_country(per_month)}, 1, ("sb",), mi(1998, 12), 25)
            b = bucket_series(C, RollingSpec("country", 1, ("sb",), 25, 12, 0), H)
            got = b[mi(1993, 1)]
            self.assertTrue(got.startswith("active-"), got)
            self.assertTrue(got.endswith(f"|{expect}"), f"{per_month and 'case'}: {got}")

    def test_sum_active_without_hit_months_reads_low_tempo(self):
        from wopr.engine.rolling import prefixes

        # 12 × 3 deaths = 36 ≥ 25 in sum, but no single month crosses 25
        dribble = {(1992, m): 3 for m in range(1, 13)}
        C, H = prefixes({1: monthly_country(dribble)}, 1, ("sb",), mi(1998, 12), 25)
        b = bucket_series(C, RollingSpec("country", 1, ("sb",), 25, 12, 0), H)
        self.assertEqual(b[mi(1993, 1)], "active-1|low")


class TestRate(unittest.TestCase):
    def substrate(self):
        quiet = {(1990, 1): 0}
        return substrate_with(
            {
                1: ("Africa", STEADY),
                2: ("Africa", {(y, m): 8 for y in range(1992, 1996) for m in range(1, 13)}),  # 96/yr
                3: ("Africa", quiet),
                4: ("Africa", quiet),
            }
        )

    def test_shorter_windows_price_lower(self):
        sub, monthly = self.substrate()
        p12 = rate(RollingSpec("country", 1, ("sb",), 25, 12, mi(1995, 6)), sub, monthly)["p"]
        p3 = rate(RollingSpec("country", 1, ("sb",), 25, 3, mi(1995, 6)), sub, monthly)["p"]
        self.assertLessEqual(p3, p12)

    def test_provisional_note_beyond_final_data(self):
        sub, monthly = self.substrate()
        monthly["data_end"] = mi(1999, 5)  # five candidate months past final_end
        for uid in sub["country"]:
            arr = monthly["country"][uid]
            monthly["country"][uid] = arr + [None] * (monthly["data_end"] - START + 1 - len(arr))
        r = rate(RollingSpec("country", 1, ("sb",), 25, 12, mi(1999, 8)), sub, monthly)
        self.assertTrue(any("candidate" in n for n in r["notes"]))

    def test_output_shape(self):
        sub, monthly = self.substrate()
        r = rate(RollingSpec("country", 1, ("sb",), 25, 12, mi(1996, 1)), sub, monthly)
        self.assertIn("bucket_coarse", r)
        self.assertEqual(r["spec"]["window_months"], 12)
        self.assertGreater(r["p"], 0)
        self.assertLess(r["p"], 1)

    def test_rate_is_one_step_frozen_but_state_can_price_horizons(self):
        # class history: one-off 3-month bursts, then permanent quiet
        from wopr.engine.rolling import assemble, build_state

        bursts = {}
        for uid, year in ((1, 1992), (2, 1993), (3, 1994)):
            bursts[uid] = ("Africa", {(year, m): 100 for m in (1, 2, 3)})
        bursts[9] = ("Africa", {(1998, m): 100 for m in (10, 11, 12)})  # fresh burst at data end
        sub, monthly = substrate_with(bursts)
        # rate() freezes the one-step number across staleness (measured better)
        near = rate(RollingSpec("country", 9, ("sb",), 25, 1, start=mi(1999, 1)), sub, monthly)
        far = rate(RollingSpec("country", 9, ("sb",), 25, 1, start=mi(1999, 7)), sub, monthly)
        self.assertEqual(near["p"], far["p"])
        self.assertTrue(any("one-step" in n for n in far["notes"]))
        # …but the state machinery can produce true horizon curves when asked
        state = build_state("country", sub, monthly, threshold=25, window=1, gaps=(0, 6))
        p0 = assemble(state, 9, mi(1999, 1))["p"]
        p6 = assemble(state, 9, mi(1999, 7))["p"]
        self.assertGreater(p0, p6)

    def test_neighbor_suffix_on_quiet_country_next_to_war(self):
        war = {(y, m): 200 for y in range(1992, 1999) for m in range(1, 13)}
        sub, monthly = substrate_with({1: ("Africa", war), 2: ("Africa", {(1990, 1): 0}), 3: ("Africa", {(1990, 1): 0})})
        sub["neighbors"] = {2: {y: {1} for y in range(1989, 1999)}}  # 2 borders the war; 3 does not
        exposed_r = rate(RollingSpec("country", 2, ("sb",), 25, 12, mi(1996, 1)), sub, monthly)
        isolated = rate(RollingSpec("country", 3, ("sb",), 25, 12, mi(1996, 1)), sub, monthly)
        self.assertEqual(exposed_r["bucket"], "cold+nbr")
        self.assertEqual(exposed_r["bucket_coarse"], "cold")
        self.assertEqual(isolated["bucket"], "cold")
        self.assertTrue(any("neighbor" in n for n in exposed_r["notes"]))


if __name__ == "__main__":
    unittest.main()
