"""Lock-In threshold engine.

Optimal-stopping math for deciding when to "lock" a player's score during a
fantasy matchup week. With N games left and each game's score modelled as
Normal(mu, sigma), backward induction gives the minimum score worth locking
for each game:

    threshold[N]   = 0                       (last game: you must take it)
    threshold[N-1] = E[X]            = mu
    threshold[k]   = E[max(X, threshold[k+1])]

Standard library only.
"""

from __future__ import annotations

import math
from typing import List

LOCK = "LOCK"
PASS = "PASS"


def _pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def _cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _expected_max(mu: float, sigma: float, c: float) -> float:
    """E[max(X, c)] for X ~ Normal(mu, sigma)."""
    if sigma <= 0:
        return max(mu, c)
    z = (c - mu) / sigma
    return c * _cdf(z) + mu * (1.0 - _cdf(z)) + sigma * _pdf(z)


def calculate_optimal_thresholds(mu: float, sigma: float, n: int) -> List[float]:
    """Return the lock threshold for games 1..n (index 0 is game 1).

    Lock game k if its actual score is >= threshold[k]; otherwise pass and
    keep playing. The final game's threshold is 0 (it is always taken).
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    if sigma < 0:
        raise ValueError("sigma must be non-negative")

    thresholds = [0.0] * n
    # Value of continuing after game k = expected outcome of playing on optimally.
    continuation = mu  # value of the last game, seen from the one before it
    for k in range(n - 2, -1, -1):
        thresholds[k] = continuation
        continuation = _expected_max(mu, sigma, continuation)
    return thresholds


def apply_modifiers(
    mu: float,
    sigma: float,
    matchup_adjustment: float = 1.0,
    context_volatility: float = 1.0,
) -> tuple[float, float]:
    """Scale mu by Matchup_Adjustment and sigma by Context_Volatility.

    Both default to 1.0 until a data source is chosen (see README).
    """
    if matchup_adjustment <= 0 or context_volatility <= 0:
        raise ValueError("modifiers must be positive")
    return mu * matchup_adjustment, sigma * context_volatility


def lock_decision(actual_score: float, threshold: float) -> str:
    """LOCK when the actual score meets or beats the game's threshold."""
    return LOCK if actual_score >= threshold else PASS
