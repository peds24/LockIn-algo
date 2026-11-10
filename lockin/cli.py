"""Print this week's lock thresholds and LOCK/PASS calls for one roster.

    python -m lockin.cli --league 1419821416949280768 --user peds24 [--week 4]

mu/sigma come from the player's game log this season, excluding the week
being evaluated (so the thresholds are what you'd have known at the start of
it). Matchup_Adjustment and Context_Volatility stay at 1.0 for now.
"""

from __future__ import annotations

import argparse

from .engine import apply_modifiers, calculate_optimal_thresholds, lock_decision
from .sleeper import Sleeper, mu_sigma

MIN_GAMES = 3


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--league", required=True)
    ap.add_argument("--user", required=True, help="Sleeper display name")
    ap.add_argument("--week", type=int, help="default: current NBA week")
    a = ap.parse_args(argv)

    s = Sleeper(a.league)
    week = a.week or s.state()["week"]
    roster = s.roster_for(a.user)
    starters = set(roster.get("starters") or [])
    print(f"{s.league['name']} · week {week} · {a.user}\n")

    for pid in sorted(roster["players"], key=lambda p: (p not in starters, s.name(p))):
        team = s.team(pid)
        tag = "S" if pid in starters else "B"
        sched = s.team_games(team, week) if team else []
        log = s.game_log(pid)
        prior = [g.points for g in log if g.week < week]
        played = {g.date: g.points for g in log if g.week == week}
        head = f"[{tag}] {s.name(pid)} ({team or 'FA'})"
        if not sched:
            print(f"{head}: no games this week\n")
            continue
        if len(prior) < MIN_GAMES:
            print(f"{head}: only {len(prior)} prior games, skipped\n")
            continue

        mu, sigma = apply_modifiers(*mu_sigma(prior))
        th = calculate_optimal_thresholds(mu, sigma, len(sched))
        print(f"{head}  mu={mu:.1f} sigma={sigma:.1f} N={len(sched)}")
        locked = False
        for i, (g, t) in enumerate(zip(sched, th), 1):
            score = played.get(g["date"])
            if locked:
                call = "-"
            elif score is None:
                call = "pending" if g["status"] != "complete" else "DNP"
            else:
                call = lock_decision(score, t)
                locked = call == "LOCK"
            shown = "" if score is None else f"{score:5.1f}"
            print(f"   G{i} {g['date']}  threshold {t:5.1f}  score {shown:>5}  {call}")
        print()


if __name__ == "__main__":
    main()
