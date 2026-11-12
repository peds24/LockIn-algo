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

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .engine import calculate_optimal_thresholds, lock_decision

OUT_STATUSES = {"Out", "IR", "Sus", "Suspension", "NA"}
SHAKY_STATUSES = {"GTD", "DTD", "Questionable", "Doubtful"}
MATCHUP_BOUNDS = (0.85, 1.15)
PROJECTION_WEIGHT = 0.5
SHAKY_VOLATILITY = 1.25
BENCHED = "BENCHED"  # played on the bench: can't be locked, ever


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


# --- Remembered locks --------------------------------------------------------
#
# Every LOCK call is written once, as a Todoist subtask whose description holds
# a marker line, and is never recomputed:
#
#     lockin pid=4866 date=2026-11-09 score=45.0
#
# A ticked subtask means "I locked it in Sleeper": the line gets " confirmed".
# Sleeper can verify a lock only after the player's next game: a locked
# player's weekly points stay at the locked score, an unlocked one's move to
# the newest game.

_MARKER = re.compile(r"lockin\s+pid=(\S+)\s+date=(\d{4}-\d{2}-\d{2})\s+score=(-?[\d.]+)(.*)")

VERIFIED = "verified"    # Sleeper's points stayed at the locked score
MISSED = "missed"        # Sleeper's points moved on: the lock was not made
UNVERIFIED = "awaiting"  # no later game yet, so Sleeper can't tell


@dataclass(frozen=True)
class KnownLock:
    pid: str
    date: str
    score: float
    confirmed: bool = False


def lock_marker(pid: str, date: str, score: float) -> str:
    return f"lockin pid={pid} date={date} score={score:.1f}"


def parse_locks(text: str) -> Dict[str, KnownLock]:
    """Read marker lines (any surrounding text is ignored). Last line per player wins,
    except that a confirmed line is never downgraded by an unconfirmed duplicate."""
    out: Dict[str, KnownLock] = {}
    for m in _MARKER.finditer(text):
        pid, date, score, rest = m.groups()
        lock = KnownLock(pid, date, float(score), "confirmed" in rest.split("\n")[0])
        prev = out.get(pid)
        if prev and prev.date == date and prev.confirmed and not lock.confirmed:
            continue
        out[pid] = lock
    return out


def verify_lock(lock: KnownLock, played: Sequence[Tuple[str, float]],
                week_points: Optional[float]) -> str:
    later = [p for d, p in played if d > lock.date]
    if not later or week_points is None:
        return UNVERIFIED
    if abs(week_points - lock.score) < 0.01:
        return VERIFIED
    return MISSED


def game_call(score: float, threshold: float, starter: bool) -> str:
    """LOCK/PASS for a game a starter played; BENCHED if he was on the bench.

    A bench game can't be locked later by starting him, so it is never LOCK.
    """
    return lock_decision(score, threshold) if starter else BENCHED
