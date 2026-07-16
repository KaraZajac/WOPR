import unittest

from tocsin.pipeline.build import cow_to_gw


class TestCowToGw(unittest.TestCase):
    def test_unified_germany_maps_to_gw_260(self):
        self.assertEqual(cow_to_gw(255, 1991), 260)
        self.assertEqual(cow_to_gw(255, 2014), 260)
        # divided-era GFR/GDR codes match G-W and pass through
        self.assertEqual(cow_to_gw(260, 1975), 260)
        self.assertEqual(cow_to_gw(265, 1975), 265)

    def test_unified_yemen_maps_to_gw_678(self):
        self.assertEqual(cow_to_gw(679, 1995), 678)
        self.assertEqual(cow_to_gw(678, 1975), 678)  # YAR unchanged
        self.assertEqual(cow_to_gw(680, 1975), 680)  # YPR unchanged

    def test_serbia_rides_the_year_aware_alias(self):
        self.assertEqual(cow_to_gw(345, 1999), 345)  # Yugoslavia
        self.assertEqual(cow_to_gw(345, 2010), 340)  # Serbia after 2006

    def test_pacific_microstates_single_lookup_not_chained(self):
        # COW 970 is Nauru while G-W 970 is Kiribati — a chained/sequential
        # remap would corrupt these; the dict lookup must be simultaneous
        self.assertEqual(cow_to_gw(946, 2000), 970)  # Kiribati
        self.assertEqual(cow_to_gw(970, 2000), 971)  # Nauru
        self.assertEqual(cow_to_gw(955, 2000), 972)  # Tonga
        self.assertEqual(cow_to_gw(947, 2000), 973)  # Tuvalu

    def test_ordinary_codes_pass_through(self):
        self.assertEqual(cow_to_gw(2, 2010), 2)  # USA
        self.assertEqual(cow_to_gw(710, 2010), 710)  # China
        self.assertEqual(cow_to_gw(750, 2010), 750)  # India


if __name__ == "__main__":
    unittest.main()
