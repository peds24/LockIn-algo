import unittest

from lockin import (
    LOCK,
    PASS,
    apply_modifiers,
    calculate_optimal_thresholds,
    lock_decision,
)


class ThresholdTests(unittest.TestCase):
    def test_uat_pseudocode_values(self):
        # mu=35, sigma=8, N=4. Pseudocode gives 40.04 / 38.19 / 35.0 / 0.
        # The spec's UAT table says 38.2 / 36.7 for games 1-2: open decision.
        t = calculate_optimal_thresholds(35, 8, 4)
        self.assertAlmostEqual(t[0], 40.04, places=2)
        self.assertAlmostEqual(t[1], 38.19, places=2)
        self.assertAlmostEqual(t[2], 35.0, places=6)
        self.assertEqual(t[3], 0.0)

    def test_single_game_threshold_is_zero(self):
        self.assertEqual(calculate_optimal_thresholds(35, 8, 1), [0.0])

    def test_thresholds_decrease_through_the_week(self):
        t = calculate_optimal_thresholds(30, 10, 6)
        self.assertEqual(t, sorted(t, reverse=True))

    def test_zero_sigma_collapses_to_mean(self):
        self.assertEqual(calculate_optimal_thresholds(20, 0, 3), [20.0, 20.0, 0.0])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            calculate_optimal_thresholds(35, 8, 0)
        with self.assertRaises(ValueError):
            calculate_optimal_thresholds(35, -1, 3)

    def test_apply_modifiers(self):
        self.assertEqual(apply_modifiers(35, 8), (35, 8))
        mu, sigma = apply_modifiers(35, 8, 1.1, 1.25)
        self.assertAlmostEqual(mu, 38.5)
        self.assertAlmostEqual(sigma, 10.0)
        with self.assertRaises(ValueError):
            apply_modifiers(35, 8, 0, 1)

    def test_lock_decision(self):
        self.assertEqual(lock_decision(40.04, 40.04), LOCK)
        self.assertEqual(lock_decision(41, 40.04), LOCK)
        self.assertEqual(lock_decision(39.9, 40.04), PASS)
        self.assertEqual(lock_decision(0, 0.0), LOCK)


if __name__ == "__main__":
    unittest.main()
