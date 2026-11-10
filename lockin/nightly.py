"""Nightly review: LOCK or PASS for every rostered player who played that day.

    python -m lockin.nightly --league 1419821416949280768 --user peds24 [--date 2026-11-09]

Without --date it reviews the most recent NBA day that has finished in
America/Mexico_City: before noon that is yesterday, from noon on it is today.
It also re-checks the day before, so a score Sleeper revised overnight shows up.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import List, Optional
from zoneinfo import ZoneInfo

from .report import BENCH, PlayerReport, week_report
from .sleeper import Sleeper

TZ = ZoneInfo("America/Mexico_City")


def default_date(now: Optional[dt.datetime] = None) -> str:
    now = now or dt.datetime.now(TZ)
    day = now.date() if now.hour >= 12 else now.date() - dt.timedelta(days=1)
    return day.isoformat()


def week_of(s: Sleeper, date: str) -> Optional[int]:
    return next((g["week"] for g in s.schedule() if g["date"] == date), None)


def day_lines(reports: List[PlayerReport], date: str) -> List[str]:
    lines = []
    for r in reports:
        g = next((g for g in r.games if g.date == date), None)
        if g is None:
            continue
        who = f"{r.name}{'' if r.starter else ' (bench)'}"
        if r.sleeper_locked_on and r.sleeper_locked_on < date:
            lines.append(f"  -      {who}: already locked on {r.sleeper_locked_on}")
        elif g.call == "-":
            first = next(x for x in r.games if x.call in ("LOCK", BENCH))
            lines.append(f"  -      {who}: engine said LOCK on {first.date} ({first.score:.1f})")
        elif g.score is None:
            lines.append(f"  -      {who}: no score yet ({g.call})")
        else:
            left = sum(1 for x in r.games if x.date > date and x.expected)
            cmp = ">=" if g.call in ("LOCK", BENCH) else "<"
            lines.append(f"  {g.call:<6} {who}: {g.score:.1f} {cmp} {g.threshold:.1f}"
                         f" · {left} game{'s' if left != 1 else ''} left")
    order = {"LOCK": 0, "BENCH": 1, "PASS": 2}
    return sorted(lines, key=lambda l: order.get(l.split()[0], 3))


def review(s: Sleeper, user: str, date: str) -> List[str]:
    week = week_of(s, date)
    if week is None:
        return [f"No NBA games on {date}."]
    return day_lines(week_report(s, user, week), date) or [f"None of your players played on {date}."]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--league", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--date", help="YYYY-MM-DD (game date); default: last finished day")
    a = ap.parse_args(argv)

    date = a.date or default_date()
    prev = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
    s = Sleeper(a.league)
    print(f"Lock-In · {s.league['name']} · games of {date}")
    print("\n".join(review(s, a.user, date)))
    print(f"\nRe-check {prev} (current scores):")
    print("\n".join(review(s, a.user, prev)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
