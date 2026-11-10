"""Evaluate one roster for one matchup week: thresholds and LOCK/PASS per game."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .engine import LOCK, apply_modifiers, lock_decision
from .model import (
    context_volatility,
    expected_games,
    locked_date,
    matchup_adjustment,
    threshold_for,
)
from .sleeper import Sleeper, mu_sigma

MIN_GAMES = 3
BENCH = "BENCH"  # would LOCK, but he is not in a starting slot


@dataclass
class GameRow:
    date: str
    expected: bool
    threshold: float
    score: Optional[float]
    call: str  # LOCK, PASS, BENCH, pending, out, DNP, "-" (already locked)


@dataclass
class PlayerReport:
    pid: str
    name: str
    team: Optional[str]
    starter: bool
    injury: Optional[str]
    note: str = ""
    mu: float = 0.0
    sigma: float = 0.0
    matchup_adj: float = 1.0
    volatility: float = 1.0
    sleeper_locked_on: Optional[str] = None
    games: List[GameRow] = field(default_factory=list)


def week_report(s: Sleeper, user: str, week: int) -> List[PlayerReport]:
    roster = s.roster_for(user)
    matchup = next((m for m in s.matchups(week) if m["roster_id"] == roster["roster_id"]), {})
    starters = set(matchup.get("starters") or roster.get("starters") or [])
    week_points = matchup.get("players_points") or {}
    proj = s.projections(week)

    reports = []
    for pid in sorted(roster["players"], key=lambda p: (p not in starters, s.name(p))):
        team, injury = s.team(pid), s.injury_status(pid)
        r = PlayerReport(pid, s.name(pid), team, pid in starters, injury)
        reports.append(r)

        sched = s.team_games(team, week) if team else []
        if not sched:
            r.note = "no games this week"
            continue
        log = s.game_log(pid)
        prior = [g.points for g in log if g.week < week]
        if len(prior) < MIN_GAMES:
            r.note = f"only {len(prior)} prior games"
            continue

        played = [(g.date, g.points) for g in log if g.week == week]
        scores = dict(played)
        r.sleeper_locked_on = locked_date(played, week_points.get(pid))

        p = proj.get(pid, {})
        dates = [g["date"] for g in sched]
        expected = expected_games(dates, {d: v["plays"] for d, v in p.items()}, injury)
        base_mu, base_sigma = mu_sigma(prior)
        r.matchup_adj = matchup_adjustment(
            [p[d]["points"] for d in expected if d in p and p[d]["points"] is not None], base_mu
        )
        r.volatility = context_volatility(injury)
        r.mu, r.sigma = apply_modifiers(base_mu, base_sigma, r.matchup_adj, r.volatility)

        locked = False
        for g in sched:
            d = g["date"]
            t = threshold_for(r.mu, r.sigma, sum(1 for e in expected if e > d))
            score = scores.get(d)
            if locked:
                call = "-"
            elif score is not None:
                call = lock_decision(score, t)
                locked = call == LOCK
                if locked and not r.starter:
                    call = BENCH
            elif g["status"] == "complete":
                call = "DNP"
            else:
                call = "pending" if d in expected else "out"
            r.games.append(GameRow(d, d in expected, t, score, call))
    return reports


def format_week(reports: List[PlayerReport]) -> str:
    lines = []
    for r in reports:
        head = f"[{'S' if r.starter else 'B'}] {r.name} ({r.team or 'FA'})"
        if r.injury:
            head += f" [{r.injury}]"
        if r.note:
            lines += [f"{head}: {r.note}", ""]
            continue
        head += (f"  mu={r.mu:.1f} sigma={r.sigma:.1f}"
                 f"  (matchup x{r.matchup_adj:.2f}, volatility x{r.volatility:.2f})")
        if r.sleeper_locked_on:
            head += f"  · Sleeper: locked {r.sleeper_locked_on}"
        lines.append(head)
        for i, g in enumerate(r.games, 1):
            sc = "" if g.score is None else f"{g.score:5.1f}"
            lines.append(f"   G{i} {g.date}  threshold {g.threshold:5.1f}  score {sc:>5}  {g.call}")
        lines.append("")
    return "\n".join(lines)
