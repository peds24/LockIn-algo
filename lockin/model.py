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
  player already locked is skipped.
- Bench games can't be locked: a game played while the player sits on the
  bench is gone. Moving him into the lineup afterwards does not let you lock
  it; he can only be started and judged on his NEXT game. So a benched game is
  called BENCHED (never LOCK), it does not end his week, and his later games
  keep their normal thresholds.
- Who to bench: a benched player worth starting replaces the starter with the
  lowest rest-of-week value whose slot he can fill (the lineup is re-checked
  against the league's slots, so others may move into UTIL/G/F). Value with
  n expected games left is the optimal-stopping continuation value (mu for 1
  game, E[max(X, value of n-1)] for more); with none left it is the score he
  already has. Locked starters are never benched. The swap is suggested only
  if it raises the expected value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

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


# --- Who to bench -------------------------------------------------------------

FLEX_SLOTS = {"G": {"PG", "SG"}, "F": {"SF", "PF"}}


def fits(slot: str, positions: Iterable[str]) -> bool:
    if slot == "UTIL":
        return True
    return bool(set(positions) & FLEX_SLOTS.get(slot, {slot}))


def lineup_fits(slots: Sequence[str], lineup: Sequence[Sequence[str]]) -> bool:
    """Can these players (each a list of positions) fill these slots, one each?"""
    if len(lineup) > len(slots):
        return False

    def place(i: int, free: List[bool]) -> bool:
        if i == len(lineup):
            return True
        for j, slot in enumerate(slots):
            if free[j] and fits(slot, lineup[i]):
                free[j] = False
                if place(i + 1, free):
                    return True
                free[j] = True
        return False

    # Most constrained players first keeps the search tiny.
    lineup = sorted(lineup, key=lambda ps: sum(fits(s, ps) for s in slots))
    return place(0, [True] * len(slots))


def rest_of_week_value(mu: float, sigma: float, games_left: int, current: float) -> float:
    """Expected final score from here, playing the remaining games optimally."""
    return threshold_for(mu, sigma, games_left) if games_left > 0 else current


def plan_swaps(
    slots: Sequence[str],
    starters: Dict[str, Tuple[Sequence[str], Optional[float], bool]],
    bench: Dict[str, Tuple[Sequence[str], float]],
) -> Dict[str, Tuple[Optional[str], Optional[float]]]:
    """For each bench player, the starter to bench for him (or None to keep him out).

    starters: pid -> (positions, value or None if unknown, locked)
    bench:    pid -> (positions, value)
    Returns pid -> (starter to bench, that starter's value). When no swap helps,
    the starter is None and the value is the weakest swappable starter's (None
    if nobody can be swapped). Best bench players claim starters first.
    """
    lineup = {pid: list(ps) for pid, (ps, _, _) in starters.items()}
    taken: Set[str] = set()
    out: Dict[str, Tuple[Optional[str], Optional[float]]] = {}
    for b, (b_pos, b_val) in sorted(bench.items(), key=lambda kv: -kv[1][1]):
        options = []
        for s, (_, s_val, locked) in starters.items():
            if locked or s_val is None or s in taken:
                continue
            trial = [ps for pid, ps in lineup.items() if pid != s] + [list(b_pos)]
            if lineup_fits(slots, trial):
                options.append((s_val, s))
        if not options:
            out[b] = (None, None)
            continue
        s_val, s = min(options)
        if b_val > s_val:
            taken.add(s)
            del lineup[s]
            lineup[b] = list(b_pos)
            out[b] = (s, s_val)
        else:
            out[b] = (None, s_val)
    return out
