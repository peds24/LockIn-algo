"""Rules that turn Sleeper data into engine inputs. Pure functions, no I/O.

Decisions (recorded in the project doc):

- Games left: a threshold depends only on how many games the player is still
  expected to play AFTER the one being judged. A scheduled game counts only if
  Sleeper's projection for it says he plays (gp=1). With no projection, it
  counts unless he is listed Out/IR/Sus.
- Matchup_Adjustment: half-weight blend of Sleeper's (Rotowire) projection
  with mu: 1 + 0.5 * (mean projected points for the week's expected games / mu
  - 1), clamped to [0.85, 1.15]. 1.0 when nothing is projected. Half weight
  because the projection is a different model on a slightly different scale.
- Lock state: Sleeper's API has no lock flag, so a lock is inferred from the
  weekly points (see locked_date). Treat it as a hint.
- Context_Volatility: 1.25 when the player is GTD/DTD/Questionable/Doubtful
  (minutes are uncertain), else 1.0.
- Substitutions: mu and sigma belong to the player, not the lineup slot, so a
  swap never changes them. The incoming player gets his own games left. A
  player already locked is skipped. A LOCK call for a benched player is shown
  as BENCH: it only scores if he is in a starting slot.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .engine import calculate_optimal_thresholds

OUT_STATUSES = {"Out", "IR", "Sus", "Suspension", "NA"}
SHAKY_STATUSES = {"GTD", "DTD", "Questionable", "Doubtful"}
MATCHUP_BOUNDS = (0.85, 1.15)
PROJECTION_WEIGHT = 0.5
SHAKY_VOLATILITY = 1.25


def expected_games(
    dates: Iterable[str],
    plays: Dict[str, Optional[bool]],
    injury_status: Optional[str],
) -> List[str]:
    """Scheduled dates the player is expected to play.

    `plays[date]` is True/False from a projection, or missing/None when the
    projection says nothing; then the injury status decides.
    """
    out = injury_status in OUT_STATUSES
    return [d for d in dates if (plays.get(d) if plays.get(d) is not None else not out)]


def threshold_for(mu: float, sigma: float, games_after: int) -> float:
    """Lock threshold for a game with `games_after` expected games still to come."""
    return calculate_optimal_thresholds(mu, sigma, games_after + 1)[0]


def matchup_adjustment(projected_points: Sequence[float], mu: float) -> float:
    if not projected_points or mu <= 0:
        return 1.0
    lo, hi = MATCHUP_BOUNDS
    ratio = (sum(projected_points) / len(projected_points)) / mu
    return round(min(hi, max(lo, 1 + PROJECTION_WEIGHT * (ratio - 1))), 3)


def context_volatility(injury_status: Optional[str]) -> float:
    return SHAKY_VOLATILITY if injury_status in SHAKY_STATUSES else 1.0


def locked_date(played: Sequence[Tuple[str, float]], week_points: Optional[float]) -> Optional[str]:
    """Infer an earlier lock from Sleeper's weekly points for the player.

    Unlocked players score their latest game. If the weekly points equal an
    earlier game's score but not the latest one, that earlier game was locked.
    `played` is (date, points) in date order.
    """
    if week_points is None or len(played) < 2:
        return None
    if abs(played[-1][1] - week_points) < 0.01:
        return None
    for date, pts in played[:-1]:
        if abs(pts - week_points) < 0.01:
            return date
    return None
