import unittest

from tocsin.engine import protocol
from tocsin.engine.baserate import Spec, Unit, bucket_of


class TestYouthHook(unittest.TestCase):
    def test_youth_refines_non_active_only(self):
        u = Unit(1, "U1", ["Africa"], 2000, 2020)
        u.years = {y: {"acd": 0, "sb": 0} for y in range(2000, 2021)}
        u.years[2019] = {"acd": 1, "sb": 500}  # active in 2019
        s = Spec("country", 1, "acd-active", (), 25, 2021, (2000, 2020))
        young = {(1, 2010)}  # young entering 2011
        # non-active year gets the youth suffix
        self.assertEqual(bucket_of(u, 2011, s, flag=young), "cold%f")
        self.assertEqual(bucket_of(u, 2012, s, flag=young), "cold%o")  # not in set
        # active buckets never get it (youth predicts onset, not continuation)
        self.assertFalse(bucket_of(u, 2020, s, flag=young).startswith("active") and "%" in bucket_of(u, 2020, s, flag=young))
        b2020 = bucket_of(u, 2020, s, flag={(1, 2019)})
        self.assertNotIn("%", b2020)

    def test_off_by_default(self):
        u = Unit(1, "U1", ["Africa"], 2000, 2020)
        u.years = {y: {"acd": 0, "sb": 0} for y in range(2000, 2021)}
        s = Spec("country", 1, "acd-active", (), 25, 2021, (2000, 2020))
        self.assertNotIn("%", bucket_of(u, 2011, s))  # youth=None → no suffix


class TestSplitLogic(unittest.TestCase):
    def test_young_set_uses_tune_years_only(self):
        # tune-era (<=2007) values: [10, 20, 30, 40]; pctl 0.5 -> cut = index 2 = 30
        youth = {(1, 2000): 10, (2, 2001): 20, (3, 2002): 30, (4, 2003): 40, (9, 2015): 35, (8, 2015): 25}
        s = protocol.young_set(youth, 0.50, 2007)
        self.assertIn((4, 2003), s)  # 40 > 30 cut
        self.assertNotIn((3, 2002), s)  # 30 not > 30
        # validate-era units classified by the TUNE-derived cut, not their own values
        self.assertIn((9, 2015), s)  # 35 > 30
        self.assertNotIn((8, 2015), s)  # 25 < 30

    def test_split_brier_partitions_by_year(self):
        recs = [
            {"year": 2005, "p": 0.5, "outcome": 1},
            {"year": 2010, "p": 0.5, "outcome": 0},
        ]
        tune, nt = protocol.split_brier(recs, hi=2007)
        val, nv = protocol.split_brier(recs, lo=2008)
        self.assertEqual((nt, nv), (1, 1))
        self.assertAlmostEqual(tune, 0.25)
        self.assertAlmostEqual(val, 0.25)


if __name__ == "__main__":
    unittest.main()
