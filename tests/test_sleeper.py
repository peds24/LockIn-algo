import unittest

from lockin.sleeper import fantasy_points, mu_sigma

# Bowl Nowheres scoring_settings (Sleeper league 1419821416949280768).
SCORING = {
    "ast": 1.0, "blk": 2.0, "bonus_pt_40p": 2.0, "bonus_pt_50p": 2.0, "dd": 1.0,
    "ff": -2.0, "pts": 0.5, "reb": 1.0, "stl": 2.0, "td": 2.0, "tf": -2.0,
    "to": -1.0, "tpm": 0.5,
}


class ScoringTests(unittest.TestCase):
    def test_plain_line(self):
        # Kyrie Irving, 2026-11-09: 35 pts, 4 ast, 2 to, 7 tpm.
        self.assertEqual(fantasy_points({"pts": 35, "ast": 4, "to": 2, "tpm": 7}, SCORING), 23.0)

    def test_bonuses_and_unscored_keys(self):
        line = {"pts": 42, "reb": 10, "ast": 3, "dd": 1, "bonus_pt_40p": 1, "min": 36, "fga": 25}
        self.assertEqual(fantasy_points(line, SCORING), 21 + 10 + 3 + 1 + 2)

    def test_mu_sigma(self):
        mu, sigma = mu_sigma([20, 30, 40])
        self.assertEqual(mu, 30)
        self.assertEqual(sigma, 10)
        self.assertEqual(mu_sigma([25]), (25, 0.0))
        with self.assertRaises(ValueError):
            mu_sigma([])


if __name__ == "__main__":
    unittest.main()
