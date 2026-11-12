"""Nightly review: LOCK or PASS for every rostered player who played that day.

    python -m lockin.nightly --league 1419821416949280768 --user peds24 \\
        [--date 2026-11-09] [--locks locks.txt] [--json-out new_locks.json]

Without --date it reviews the most recent NBA day that has finished in
America/Mexico_City: before noon that is yesterday, from noon on it is today.
It also re-checks the day before, so a score Sleeper revised overnight shows up.

--locks: a text file holding this week's remembered LOCK calls, one marker line
each (`lockin pid=... date=... score=...`, plus ` confirmed` when you ticked it
off). These calls are never recomputed. Each is checked against Sleeper once the
player has played again.

--json-out: writes the NEW LOCK calls for the reviewed date, each with the
marker line to store, so the caller can remember them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from .engine import LOCK
from .model import (BENCHED, MISSED, VERIFIED, KnownLock, lock_marker, parse_locks, plan_swaps,
                    rest_of_week_value)
from .report import PlayerReport, week_report
from .sleeper import Sleeper

TZ = ZoneInfo("America/Mexico_City")


def default_date(now: Optional[dt.datetime] = None) -> str:
    now = now or dt.datetime.now(TZ)
    day = now.date() if now.hour >= 12 else now.date() - dt.timedelta(days=1)
    return day.isoformat()


def week_of(s: Sleeper, date: str) -> Optional[int]:
    return next((g["week"] for g in s.schedule() if g["date"] == date), None)


def _locked(r: PlayerReport, date: str) -> bool:
    if r.sleeper_locked_on and r.sleeper_locked_on <= date:
        return True
    return any(g.call == "LOCK" and g.date <= date for g in r.games)


def _value(r: PlayerReport, date: str) -> Optional[float]:
    """Expected rest-of-week score after `date`; None when there's no model for him."""
    left = sum(1 for g in r.games if g.expected and g.date > date)
    if r.note and r.note != "no games this week":
        return 0.0 if r.injury in ("Out", "IR") else None
    current = next((g.score for g in reversed(r.games) if g.date <= date and g.score is not None), 0.0)
    return rest_of_week_value(r.mu, r.sigma, left, current)


def swaps(reports: List[PlayerReport], date: str, slots: Sequence[str]) -> Dict[str, Tuple[Optional[str], Optional[float]]]:
    """Bench player pid -> (starter pid to bench for him or None, that starter's value)."""
    starters = {r.pid: (r.positions, _value(r, date), _locked(r, date)) for r in reports if r.starter}
    bench = {}
    for r in reports:
        v = _value(r, date)
        if not r.starter and v is not None and any(g.expected and g.date > date for g in r.games):
            bench[r.pid] = (r.positions, v)
    return plan_swaps(slots, starters, bench)


def day_lines(reports: List[PlayerReport], date: str, slots: Sequence[str] = ()) -> List[str]:
    plan = swaps(reports, date, slots) if slots else {}
    names = {r.pid: r.name for r in reports}
    lines = []
    for r in reports:
        g = next((g for g in r.games if g.date == date), None)
        if g is None:
            continue
        who = f"{r.name}{'' if r.starter else ' (bench)'}"
        if r.lock and r.lock.date < date and r.lock_status != MISSED:
            lines.append(f"  -       {who}: locked on {r.lock.date} ({r.lock.score:.1f})")
        elif not r.lock and r.sleeper_locked_on and r.sleeper_locked_on < date:
            lines.append(f"  -       {who}: Sleeper shows a lock on {r.sleeper_locked_on}")
        elif g.call == "-":
            first = next(x for x in r.games if x.call == LOCK)
            lines.append(f"  -       {who}: engine said LOCK on {first.date} ({first.score:.1f})")
        elif g.score is None:
            lines.append(f"  -       {who}: no score yet ({g.call})")
        elif g.call == BENCHED:
            nxt = next((x for x in r.games if x.date > date and x.expected), None)
            out, out_val = plan.get(r.pid, (None, None))
            mine = _value(r, date)
            if not nxt:
                tip = "no games left this week"
            elif out:
                tip = (f"start him for {nxt.date}, bench {names[out]}"
                       f" (rest of week ~{mine:.1f} vs ~{out_val:.1f})")
            elif out_val is not None:
                tip = f"keep him benched (~{mine:.1f}, your weakest swappable starter is ~{out_val:.1f})"
            else:
                tip = "keep him benched (no unlocked starter he can replace)"
            lines.append(f"  {BENCHED:<7} {who}: {g.score:.1f} on the bench, can't be locked"
                         f" · {tip}")
        else:
            left = sum(1 for x in r.games if x.date > date and x.expected)
            cmp = ">=" if g.call == LOCK else "<"
            lines.append(f"  {g.call:<7} {who}: {g.score:.1f} {cmp} {g.threshold:.1f}"
                         f" · {left} game{'s' if left != 1 else ''} left")
    order = {LOCK: 0, "PASS": 1, BENCHED: 2}
    return sorted(lines, key=lambda l: order.get(l.split()[0], 3))


def lock_lines(reports: List[PlayerReport]) -> List[str]:
    out = []
    for r in sorted((r for r in reports if r.lock), key=lambda r: (r.lock_status != MISSED, r.name)):
        you = ", you confirmed" if r.lock.confirmed else ""
        if r.lock_status == MISSED:
            out.append(f"  !! {r.name}: lock on {r.lock.date} ({r.lock.score:.1f}) NOT in Sleeper{you}"
                       f" · now scoring {r.week_points:.1f}. Treated as unlocked.")
        elif r.lock_status == VERIFIED:
            out.append(f"  ok {r.name}: {r.lock.date} ({r.lock.score:.1f}) confirmed by Sleeper")
        else:
            out.append(f"  .. {r.name}: {r.lock.date} ({r.lock.score:.1f}) · Sleeper can't confirm"
                       f" until his next game{you}")
    return out


def new_calls(reports: List[PlayerReport], date: str) -> List[dict]:
    calls = []
    for r in reports:
        g = next((g for g in r.games if g.date == date), None)
        if g is None or g.call != LOCK or (r.lock and r.lock.date == date):
            continue
        if not r.lock and r.sleeper_locked_on and r.sleeper_locked_on < date:
            continue  # Sleeper already shows an earlier lock
        if not any(x.date > date and x.expected for x in r.games):
            continue  # his last game of the week counts anyway: nothing to do
        calls.append({
            "pid": r.pid, "name": r.name, "date": date, "score": g.score,
            "threshold": round(g.threshold, 1), "bench": False,  # bench games are never locked (BENCHED)
            "marker": lock_marker(r.pid, date, g.score),
        })
    return calls


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--league", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--date", help="YYYY-MM-DD (game date); default: last finished day")
    ap.add_argument("--locks", type=Path, help="file with remembered lock marker lines")
    ap.add_argument("--json-out", type=Path, help="write new LOCK calls here")
    a = ap.parse_args(argv)

    known: Dict[str, KnownLock] = parse_locks(a.locks.read_text()) if a.locks else {}
    date = a.date or default_date()
    prev = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
    s = Sleeper(a.league)

    print(f"Lock-In · {s.league['name']} · games of {date}")
    week = week_of(s, date)
    reports = week_report(s, a.user, week, known) if week is not None else []
    slots = [p for p in s.league.get("roster_positions", []) if p not in ("BN", "IR")]
    if week is None:
        print(f"No NBA games on {date}.")
    else:
        print("\n".join(day_lines(reports, date, slots)) or f"None of your players played on {date}.")
        locks = lock_lines(reports)
        if locks:
            print("\nLocks this week:")
            print("\n".join(locks))

    print(f"\nRe-check {prev} (current scores):")
    pweek = week_of(s, prev)
    if pweek is None:
        print(f"No NBA games on {prev}.")
    else:
        preports = reports if pweek == week else week_report(s, a.user, pweek, known)
        print("\n".join(day_lines(preports, prev, slots)) or f"None of your players played on {prev}.")

    if a.json_out:
        a.json_out.write_text(json.dumps(new_calls(reports, date), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
