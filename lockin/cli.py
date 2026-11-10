"""Print a matchup week's lock thresholds and LOCK/PASS calls for one roster.

    python -m lockin.cli --league 1419821416949280768 --user peds24 [--week 4]

mu/sigma come from the player's games in earlier weeks, then are scaled by
Matchup_Adjustment and Context_Volatility (see lockin/model.py).
"""

from __future__ import annotations

import argparse

from .report import format_week, week_report
from .sleeper import Sleeper


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--league", required=True)
    ap.add_argument("--user", required=True, help="Sleeper display name")
    ap.add_argument("--week", type=int, help="default: current NBA week")
    a = ap.parse_args(argv)

    s = Sleeper(a.league)
    week = a.week or s.state()["week"]
    print(f"{s.league['name']} · week {week} · {a.user}\n")
    print(format_week(week_report(s, a.user, week)))


if __name__ == "__main__":
    main()
