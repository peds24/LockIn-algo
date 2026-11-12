import datetime as dt
import unittest

from lockin.engine import calculate_optimal_thresholds
from lockin.model import (
    BENCHED,
    game_call,
    fits,
    lineup_fits,
    plan_swaps,
    rest_of_week_value,
    context_volatility,
    expected_games,
    locked_date,
    matchup_adjustment,
    threshold_for,
)
from lockin.nightly import TZ, default_date

DATES = ["2026-11-09", "2026-11-11", "2026-11-13", "2026-11-15"]


class ExpectedGamesTests(unittest.TestCase):
    def test_projection_decides(self):
        plays = {"2026-11-11": False, "2026-11-13": True}
        self.assertEqual(expected_games(DATES, plays, None),
                         ["2026-11-09", "2026-11-13", "2026-11-15"])

    def test_out_without_projection(self):
        self.assertEqual(expected_games(DATES, {}, "Out"), [])
        # A projection that says he plays overrides the stale status.
        self.assertEqual(expected_games(DATES, {"2026-11-15": True}, "Out"), ["2026-11-15"])


class ThresholdTests(unittest.TestCase):
    def test_missed_future_game_lowers_threshold(self):
        # Game 1 of 4 normally keeps 3 games after it; if he misses one, only 2.
        full = calculate_optimal_thresholds(35, 8, 4)
        self.assertAlmostEqual(threshold_for(35, 8, 3), full[0])
        self.assertAlmostEqual(threshold_for(35, 8, 2), full[1])
        self.assertEqual(threshold_for(35, 8, 0), 0.0)


class BenchTests(unittest.TestCase):
    def test_bench_game_never_locks(self):
        self.assertEqual(game_call(50.0, 30.0, starter=True), "LOCK")
        self.assertEqual(game_call(20.0, 30.0, starter=True), "PASS")
        # Even a monster game on the bench can't be locked by starting him later.
        self.assertEqual(game_call(50.0, 30.0, starter=False), BENCHED)
        self.assertEqual(game_call(50.0, 0.0, starter=False), BENCHED)


SLOTS = ["PG", "SG", "G", "SF", "PF", "F", "C", "UTIL", "UTIL"]
GUARD, WING, BIG = ["PG", "SG"], ["SF", "PF"], ["C"]


class WhoToBenchTests(unittest.TestCase):
    def test_slot_fit(self):
        self.assertTrue(fits("G", ["SG"]))
        self.assertFalse(fits("F", ["C"]))
        self.assertTrue(fits("UTIL", ["C"]))
        self.assertTrue(lineup_fits(SLOTS, [GUARD] * 3 + [WING] * 3 + [BIG] * 3))
        self.assertFalse(lineup_fits(SLOTS, [BIG] * 4 + [GUARD] * 5))  # only C + 2 UTIL take bigs

    def test_value(self):
        self.assertEqual(rest_of_week_value(30, 8, 0, 22.0), 22.0)  # done: keeps his score
        self.assertEqual(rest_of_week_value(30, 8, 1, 22.0), 30)    # one game: mu
        self.assertGreater(rest_of_week_value(30, 8, 2, 0), 30)     # more games, more upside

    def test_benches_weakest_unlocked_starter_he_can_replace(self):
        starters = {
            "g1": (GUARD, 15.0, True),   # weakest, but locked
            "g2": (GUARD, 18.0, False),
            "g3": (GUARD, 25.0, False),
            "w1": (WING, 22.0, False), "w2": (WING, 23.0, False), "w3": (WING, 24.0, False),
            "c1": (BIG, 16.0, False), "c2": (BIG, 26.0, False), "c3": (BIG, 27.0, False),
        }
        # A wing can replace the 16 center: the other bigs take C + UTIL, he takes UTIL...
        self.assertEqual(plan_swaps(SLOTS, starters, {"b": (WING, 20.0)}), {"b": ("c1", 16.0)})
        # ...and a weak bench player stays out.
        self.assertEqual(plan_swaps(SLOTS, starters, {"b": (WING, 10.0)}), {"b": (None, 16.0)})

    def test_two_bench_players_dont_share_a_starter(self):
        starters = {"s1": (GUARD, 10.0, False), "s2": (GUARD, 12.0, False)}
        plan = plan_swaps(["UTIL", "UTIL"], starters, {"a": (GUARD, 20.0), "b": (GUARD, 11.0)})
        self.assertEqual(plan, {"a": ("s1", 10.0), "b": (None, 12.0)})


class ModifierTests(unittest.TestCase):
    def test_matchup_adjustment(self):
        self.assertEqual(matchup_adjustment([], 30), 1.0)
        self.assertEqual(matchup_adjustment([33, 33], 30), 1.05)  # half of +10%
        self.assertEqual(matchup_adjustment([60], 30), 1.15)
        self.assertEqual(matchup_adjustment([10], 30), 0.85)

    def test_context_volatility(self):
        self.assertEqual(context_volatility(None), 1.0)
        self.assertEqual(context_volatility("GTD"), 1.25)
        self.assertEqual(context_volatility("Out"), 1.0)


class LockInferenceTests(unittest.TestCase):
    def test_locked_earlier(self):
        played = [("2026-11-02", 33.5), ("2026-11-04", 18.0), ("2026-11-06", 18.5)]
        self.assertEqual(locked_date(played, 33.5), "2026-11-02")

    def test_unlocked_scores_latest(self):
        played = [("2026-11-02", 30.0), ("2026-11-04", 17.0)]
        self.assertIsNone(locked_date(played, 17.0))
        self.assertIsNone(locked_date(played[:1], 30.0))
        self.assertIsNone(locked_date(played, None))


class NightlyDateTests(unittest.TestCase):
    def test_default_date(self):
        self.assertEqual(default_date(dt.datetime(2026, 11, 10, 2, 0, tzinfo=TZ)), "2026-11-09")
        self.assertEqual(default_date(dt.datetime(2026, 11, 10, 23, 0, tzinfo=TZ)), "2026-11-10")


if __name__ == "__main__":
    unittest.main()


class RememberedLockTests(unittest.TestCase):
    def test_parse_markers(self):
        from lockin.model import KnownLock, lock_marker, parse_locks
        text = ("Lock Cooper Flagg (45.0)\n" + lock_marker("4866", "2026-11-09", 45.0) + "\n"
                "something else\nlockin pid=4891 date=2026-11-09 score=30.5 confirmed\n")
        self.assertEqual(parse_locks(text), {
            "4866": KnownLock("4866", "2026-11-09", 45.0, False),
            "4891": KnownLock("4891", "2026-11-09", 30.5, True),
        })
        # A confirmed line is not downgraded by an unconfirmed copy of it.
        dup = "lockin pid=1 date=2026-11-09 score=3.0 confirmed\nlockin pid=1 date=2026-11-09 score=3.0\n"
        self.assertTrue(parse_locks(dup)["1"].confirmed)

    def test_verify(self):
        from lockin.model import MISSED, UNVERIFIED, VERIFIED, KnownLock, verify_lock
        lock = KnownLock("1", "2026-11-09", 45.0)
        self.assertEqual(verify_lock(lock, [("2026-11-09", 45.0)], 45.0), UNVERIFIED)
        played = [("2026-11-09", 45.0), ("2026-11-12", 22.0)]
        self.assertEqual(verify_lock(lock, played, 45.0), VERIFIED)
        self.assertEqual(verify_lock(lock, played, 22.0), MISSED)
