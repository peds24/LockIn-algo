"""Read-only client for Sleeper's public NBA API (no auth needed).

Endpoints verified against a live league on 2026-11-10:

    v1/league/<id>                        league settings, scoring_settings
    v1/league/<id>/rosters                players + starters per roster
    v1/league/<id>/users                  display names (owner_id -> name)
    v1/league/<id>/matchups/<week>        weekly fantasy points per player
    v1/state/nba                          current season + week
    v1/players/nba                        all players (~2.5 MB, cached daily)
    schedule/nba/regular/<season>         every game: date, week, home/away team
    stats/nba/player/<pid>?...&grouping=week   a player's game log by week
    projections/nba/<season>/<week>?season_type=regular
                                          per-game projections: gp (1 = expected to
                                          play, missing = not), projected stat line

Standard library only.
"""

from __future__ import annotations

import json
import os
import statistics
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

BASE = "https://api.sleeper.app"
CACHE_DIR = Path(os.environ.get("LOCKIN_CACHE", Path.home() / ".cache" / "lockin"))
PLAYERS_TTL_SECONDS = 24 * 3600


def _get(path: str):
    req = urllib.request.Request(f"{BASE}/{path}", headers={"User-Agent": "lockin/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


# --- Scoring -----------------------------------------------------------------


def fantasy_points(stats: Dict[str, float], scoring: Dict[str, float]) -> float:
    """Score one game's raw stat line with the league's scoring_settings.

    Sleeper already reports bonus and double/triple-double flags as stat keys
    (dd, td, bonus_pt_40p, ...), so scoring is a plain weighted sum.
    """
    return round(sum(w * stats.get(k, 0.0) for k, w in scoring.items()), 2)


def mu_sigma(scores: Iterable[float]) -> tuple[float, float]:
    """Mean and sample standard deviation of game scores."""
    s = list(scores)
    if not s:
        raise ValueError("no games")
    if len(s) == 1:
        return s[0], 0.0
    return statistics.fmean(s), statistics.stdev(s)


# --- Data access -------------------------------------------------------------


@dataclass
class Game:
    date: str
    week: int
    points: float  # fantasy points under the league's scoring


class Sleeper:
    def __init__(self, league_id: str):
        self.league_id = league_id
        self.league = _get(f"v1/league/{league_id}")
        self.scoring: Dict[str, float] = self.league["scoring_settings"]
        self.season: str = self.league["season"]
        self._players: Optional[dict] = None
        self._schedule: Optional[list] = None
        self._projections: Dict[int, Dict[str, Dict[str, dict]]] = {}

    # league
    def state(self) -> dict:
        return _get("v1/state/nba")

    def rosters(self) -> List[dict]:
        return _get(f"v1/league/{self.league_id}/rosters")

    def users(self) -> Dict[str, str]:
        return {u["user_id"]: u["display_name"] for u in _get(f"v1/league/{self.league_id}/users")}

    def matchups(self, week: int) -> List[dict]:
        return _get(f"v1/league/{self.league_id}/matchups/{week}")

    def roster_for(self, display_name: str) -> dict:
        names = self.users()
        for r in self.rosters():
            if names.get(r["owner_id"], "").lower() == display_name.lower():
                return r
        raise KeyError(f"no roster owned by {display_name!r}")

    # players
    def players(self) -> dict:
        if self._players is None:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            f = CACHE_DIR / "players_nba.json"
            if f.exists() and time.time() - f.stat().st_mtime < PLAYERS_TTL_SECONDS:
                self._players = json.loads(f.read_text())
            else:
                self._players = _get("v1/players/nba")
                f.write_text(json.dumps(self._players))
        return self._players

    def name(self, pid: str) -> str:
        p = self.players().get(pid, {})
        return p.get("full_name") or pid

    def team(self, pid: str) -> Optional[str]:
        return self.players().get(pid, {}).get("team")

    def injury_status(self, pid: str) -> Optional[str]:
        return self.players().get(pid, {}).get("injury_status")

    # projections
    def projections(self, week: int) -> Dict[str, Dict[str, dict]]:
        """{player_id: {date: {"plays": bool, "points": float | None}}}."""
        if week not in self._projections:
            out: Dict[str, Dict[str, dict]] = {}
            for e in _get(f"projections/nba/{self.season}/{week}?season_type=regular") or []:
                st = e.get("stats") or {}
                plays = bool(st.get("gp"))
                out.setdefault(e["player_id"], {})[e["date"]] = {
                    "plays": plays,
                    "points": fantasy_points(st, self.scoring) if plays else None,
                }
            self._projections[week] = out
        return self._projections[week]

    # schedule
    def schedule(self) -> list:
        if self._schedule is None:
            self._schedule = _get(f"schedule/nba/regular/{self.season}")
        return self._schedule

    def team_games(self, team: str, week: int) -> List[dict]:
        return sorted(
            (g for g in self.schedule()
             if g["week"] == week and team in (g["home"]["team"], g["away"]["team"])),
            key=lambda g: g["date"],
        )

    # stats
    def game_log(self, pid: str) -> List[Game]:
        """Every game the player has played this season, oldest first."""
        by_week = _get(
            f"stats/nba/player/{pid}?season_type=regular&season={self.season}&grouping=week"
        ) or {}
        games: List[Game] = []
        for week, entries in by_week.items():
            for e in entries or []:
                st = e.get("stats") or {}
                if not e.get("date") or not st.get("min"):
                    continue  # DNP or not played yet
                games.append(Game(e["date"], int(week), fantasy_points(st, self.scoring)))
        return sorted(games, key=lambda g: g.date)
