# Lock-In engine

Decides when to lock a player's score in a Sleeper fantasy basketball matchup week,
using optimal stopping (backward induction on a Normal(mu, sigma) score model).

Pending work is tracked in the Claude Doc "Lock-In engine: pending work for Claude Code".

## Usage

```bash
python -m lockin.cli --league 1419821416949280768 --user peds24          # this week
python -m lockin.cli --league 1419821416949280768 --user peds24 --week 3 # dry run on a past week
```

For each rostered player: mu/sigma from this season's game log (weeks before the one shown),
N = the team's games that week, the threshold per game, and LOCK/PASS for games already played.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Layout

- `lockin/engine.py`: `calculate_optimal_thresholds`, `apply_modifiers`, `lock_decision` (standard library only)
- `lockin/sleeper.py`: Sleeper public API client + league scoring (`fantasy_points`, `mu_sigma`)
- `lockin/cli.py`: weekly thresholds and LOCK/PASS for one roster
- `tests/`: 10 unit tests (offline)

## Status

- [x] Threshold engine plus tests
- [x] UAT decided: keep the pseudocode values, 40.04 / 38.19 / 35.0 / 0 (mu=35, sigma=8, N=4)
- [x] Sleeper connection: league `1419821416949280768` (Bowl Nowheres, lock-in mode). Endpoints verified; scoring reproduces Sleeper's weekly points exactly
- [x] mu/sigma: this season's game log (default; min 3 games)
- [ ] Matchup_Adjustment / Context_Volatility source (both 1.0 for now)
- [ ] Missed games (DNP/injury): rerun with N = games actually left
- [ ] Substitutions: N = scheduled games left; rerun on each swap; benched-player and mu rules
- [ ] Nightly review (America/Mexico_City): pull final scores → LOCK/PASS → notify (Todoist / push / email)
