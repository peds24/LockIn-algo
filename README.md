# Lock-In engine

Decides when to lock a player's score in a Sleeper fantasy basketball matchup week,
using optimal stopping (backward induction on a Normal(mu, sigma) score model).

Pending work is tracked in the Claude Doc "Lock-In engine: pending work for Claude Code".

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Layout

- `lockin/engine.py`: `calculate_optimal_thresholds`, `apply_modifiers`, `lock_decision` (standard library only)
- `tests/test_engine.py`: 7 unit tests

## Status

- [x] Threshold engine plus tests
- [ ] **Open decision:** spec UAT says 38.2 / 36.7 for games 1-2 (mu=35, sigma=8, N=4); the pseudocode (current behaviour) gives 40.04 / 38.19. Games 3-4 agree (35.0, 0).
- [ ] Sleeper connection: league ID, endpoints (rosters, users, matchups, players, stats), player → games-left mapping, mu/sigma source, Matchup_Adjustment / Context_Volatility source
- [ ] Substitutions: N = scheduled games left; rerun on each swap; benched-player and mu rules
- [ ] Nightly review (America/Mexico_City): pull final scores → LOCK/PASS → notify (Todoist / push / email)
