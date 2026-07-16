import datetime
import unittest

from wopr.journal.resolve import accumulate, decide, match

META = {
    "ucdp_release": "26.1",
    "annual_end": datetime.date(2025, 12, 31),
    "through": datetime.date(2026, 5, 31),
}


def ev(**kw):
    row = {
        "type_of_violence": "1",
        "country_id": "530",
        "dyad_new_id": "865",
        "conflict_new_id": "409",
        "side_a_new_id": "109",
        "side_b_new_id": "537",
        "dyad_name": "A - B",
        "side_a": "A",
        "side_b": "B",
        "conflict_name": "X: Government",
    }
    row.update(kw)
    return row


def crit(kind="country", cid=530, types=("sb",), threshold=25):
    return {
        "scope": {"kind": kind, "id": cid},
        "types": list(types),
        "measure": "deaths",
        "threshold": threshold,
    }


class TestMatch(unittest.TestCase):
    def test_country_and_type(self):
        self.assertTrue(match(ev(), crit(), 2026))
        self.assertFalse(match(ev(country_id="625"), crit(), 2026))
        self.assertFalse(match(ev(type_of_violence="2"), crit(), 2026))
        self.assertTrue(match(ev(type_of_violence="2"), crit(types=("sb", "ns")), 2026))

    def test_serbia_alias(self):
        self.assertTrue(match(ev(country_id="345"), crit(cid=340), 2010))
        self.assertFalse(match(ev(country_id="345"), crit(cid=340), 2000))
        self.assertTrue(match(ev(country_id="345"), crit(cid=345), 2000))

    def test_dyad_scope_rejects_placeholders(self):
        self.assertTrue(match(ev(), crit(kind="dyad", cid=865), 2026))
        self.assertFalse(match(ev(dyad_name="XXX700 - XXX700"), crit(kind="dyad", cid=865), 2026))

    def test_actor_scope_matches_either_side(self):
        self.assertTrue(match(ev(), crit(kind="actor", cid=537), 2026))
        self.assertFalse(match(ev(), crit(kind="actor", cid=999), 2026))


class TestAccumulate(unittest.TestCase):
    def test_cross_date_is_cumulative(self):
        d = datetime.date
        counted = [(d(2026, 3, 1), 10, False), (d(2026, 1, 1), 10, False), (d(2026, 2, 1), 10, False)]
        r = accumulate(counted, threshold=25)
        self.assertEqual(r["total"], 30)
        self.assertEqual(r["cross_date"], d(2026, 3, 1))  # sorted before summing

    def test_no_cross(self):
        r = accumulate([(datetime.date(2026, 1, 1), 10, True)], threshold=25)
        self.assertIsNone(r["cross_date"])
        self.assertTrue(r["used_provisional"])


class TestDecide(unittest.TestCase):
    def evaluation(self, cross=None, end=datetime.date(2026, 12, 31)):
        return {
            "total": 30 if cross else 5,
            "events": 3,
            "cross_date": cross,
            "used_provisional": False,
            "excluded_unattributed": 0,
            "window": (datetime.date(2026, 1, 1), end),
        }

    def test_yes_resolves_early_and_provisionally(self):
        res = decide(self.evaluation(cross=datetime.date(2026, 2, 10)), META)
        self.assertEqual(res["outcome"], "yes")
        self.assertEqual(res["decided_on"], "2026-02-10")
        self.assertTrue(res["provisional"])  # decided past the annual cutoff

    def test_yes_within_annual_is_final(self):
        ev = self.evaluation(cross=datetime.date(2025, 6, 1))
        ev["window"] = (datetime.date(2025, 1, 1), datetime.date(2025, 12, 31))
        res = decide(ev, META)
        self.assertFalse(res["provisional"])

    def test_pending_when_window_outruns_data(self):
        self.assertIsNone(decide(self.evaluation(), META))

    def test_no_when_data_covers_window(self):
        ev = self.evaluation(end=datetime.date(2026, 4, 30))
        res = decide(ev, META)
        self.assertEqual(res["outcome"], "no")
        self.assertEqual(res["decided_on"], "2026-04-30")
        self.assertTrue(res["provisional"])


if __name__ == "__main__":
    unittest.main()
