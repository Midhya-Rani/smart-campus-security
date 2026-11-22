import unittest
from datetime import datetime, time

from campus.classifier import EventClassifier, SKLEARN_AVAILABLE
from campus.database import Database
from campus.models import Alert
from campus.rules import Rule, RuleEngine, parse_time


def at(h, m=0):
    return datetime(2026, 1, 1, h, m)


class TestRules(unittest.TestCase):
    def test_window_inside_and_outside(self):
        r = Rule("Lab", time(8), time(20))
        self.assertTrue(r.is_allowed(time(8)))
        self.assertTrue(r.is_allowed(time(20)))
        self.assertFalse(r.is_allowed(time(20, 1)))
        self.assertFalse(r.is_allowed(time(3)))

    def test_window_crossing_midnight(self):
        r = Rule("Lab", time(20), time(6))
        self.assertTrue(r.is_allowed(time(23)))
        self.assertTrue(r.is_allowed(time(2)))
        self.assertFalse(r.is_allowed(time(12)))

    def test_engine(self):
        e = RuleEngine([Rule("Lab", time(8), time(20), 3)])
        alert = e.evaluate("Lab", 2, at(22))
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, 3)
        self.assertIn("2 people", alert.description)
        self.assertIsNone(e.evaluate("Lab", 2, at(12)))       # allowed time
        self.assertIsNone(e.evaluate("Lab", 0, at(22)))       # nobody there
        self.assertIsNone(e.evaluate("Cafeteria", 1, at(22)))  # no rule
        e.rules["Lab"].enabled = False
        self.assertIsNone(e.evaluate("Lab", 1, at(22)))

    def test_parse_time(self):
        self.assertEqual(parse_time("07:05"), time(7, 5))
        with self.assertRaises(ValueError):
            parse_time("25:99")


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def test_events_roundtrip_and_status(self):
        a = Alert("Lab", "night visit", 3, at(23), 2, "Intrusion")
        a.id = self.db.add_event(a)
        got = self.db.get_events()[0]
        self.assertEqual((got.location, got.severity, got.person_count, got.timestamp),
                         ("Lab", 3, 2, at(23)))
        self.assertEqual(self.db.count_events(status="pending"), 1)
        self.db.set_status(a.id, "reviewed")
        self.assertEqual(self.db.count_events(status="pending"), 0)
        self.assertEqual(self.db.count_events(min_severity=3), 1)

    def test_dataframe(self):
        self.assertTrue(self.db.events_dataframe().empty)
        self.db.add_event(Alert("Lab", "x", 2, at(23)))
        df = self.db.events_dataframe()
        self.assertEqual(int(df.loc[0, "hour"]), 23)

    def test_rules_upsert_and_delete(self):
        self.db.save_rule(Rule("Lab", time(8), time(20), 3))
        self.db.save_rule(Rule("Lab", time(9), time(18), 2, False))   # update same location
        rules = self.db.get_rules()
        self.assertEqual(len(rules), 1)
        self.assertEqual((rules[0].allowed_from, rules[0].severity, rules[0].enabled),
                         (time(9), 2, False))
        self.db.delete_rule("Lab")
        self.assertEqual(self.db.get_rules(), [])


@unittest.skipUnless(SKLEARN_AVAILABLE, "scikit-learn not installed")
class TestClassifier(unittest.TestCase):
    def test_trains_and_predicts(self):
        clf = EventClassifier()
        self.assertGreater(clf.train(), 0.9)
        self.assertEqual(clf.predict(2, 1, 3), "Intrusion")
        self.assertEqual(clf.predict(12, 1, 1), "Routine")


if __name__ == "__main__":
    unittest.main()
