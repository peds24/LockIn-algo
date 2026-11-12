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
scaled by Matchup_Adjustment and Context_Volatility, the threshold per game, and LOCK/PASS for
games already played.

Nightly review (the games of the last finished day in America/Mexico_City, plus a re-check of
the day before for revised scores):

```bash
python -m lockin.nightly --league 1419821416949280768 --user peds24 [--date 2026-11-09]
```

Rules (details in `lockin/model.py`):

- **Games left:** a game's threshold uses the games the player is still expected to play after it.
  A scheduled game counts only if Sleeper's projection says he plays (gp=1); without a projection,
  Out/IR players count as not playing.
- **Matchup_Adjustment:** half-weight blend of Sleeper's per-game projection with mu, capped at ±15%.
- **Context_Volatility:** sigma × 1.25 for GTD/DTD/Questionable/Doubtful players, else 1.0.
- **Substitutions:** mu/sigma belong to the player, so a swap doesn't change them; the incoming
  player uses his own games left. Players already locked are skipped.
- **Bench games can't be locked:** a game he plays on the bench shows as BENCHED. Starting him
  afterwards doesn't let you lock it; he can only be started for his next game, so his week stays
  open and later games keep their normal thresholds. The nightly review says which game to start
  him for. Starter/bench comes from the current lineup (Sleeper keeps no per-day lineup history).
- **Remembered locks:** Sleeper's API has no lock flag, so every LOCK call is stored once as a
  Todoist subtask whose description holds a marker line (`lockin pid=... date=... score=...`) and is
  never recomputed. Pass this week's markers with `--locks FILE` (append ` confirmed` for ticked
  subtasks); `--json-out FILE` writes the new calls with their markers.
- **Verification:** after the player's next game, Sleeper's weekly points show whether the lock was
  made (they stay at the locked score). A lock Sleeper contradicts is flagged `!!` and the player is
  evaluated again. Locks made without a call are inferred from the same points, as a hint only.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Layout

- `lockin/engine.py`: `calculate_optimal_thresholds`, `apply_modifiers`, `lock_decision` (standard library only)
- `lockin/sleeper.py`: Sleeper public API client + league scoring (`fantasy_points`, `mu_sigma`)
- `lockin/model.py`: games-left, modifier, substitution and lock-inference rules (pure)
- `lockin/report.py`: one roster × one week → thresholds and calls
- `lockin/cli.py`: weekly view · `lockin/nightly.py`: nightly LOCK/PASS review
- `tests/`: 21 unit tests (offline)

## Status

- [x] Threshold engine plus tests
- [x] UAT decided: keep the pseudocode values, 40.04 / 38.19 / 35.0 / 0 (mu=35, sigma=8, N=4)
- [x] Sleeper connection: league `1419821416949280768` (Bowl Nowheres, lock-in mode). Endpoints verified; scoring reproduces Sleeper's weekly points exactly
- [x] mu/sigma: this season's game log (default; min 3 games)
- [x] Matchup_Adjustment (Sleeper projections) and Context_Volatility (injury status)
- [x] Missed games: games left = games he's projected to play
- [x] Substitution rules
- [x] Nightly review script
- [x] Nightly schedule (cloud, 1:10am America/Mexico_City) → Todoist project Lock-In
- [x] Remembered locks + Sleeper verification
