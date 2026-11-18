# Griffith crack (strain-controlled)

LAMMPS simulations of a notched Cu slab under cyclic strain. `metric.py`
decides whether the notch grew and writes the result to each run's
`damage.json`.

Each contribution's `identifier` is `mp-30` (FCC Cu, Fm-3m); `data.runId` is
the unique per-run key.

## Models

- `schema.py`: `CrackSimulation`, one per run (the contribution's `data`),
  with nested `params`, `grid`, `verdict` (with `diagnostics`), `earlyStop`
  and `truncated`.
- `frame.py`: `CrackFrame`, one table row per analyzed frame.
  `validate_simulation(sim, frames)` checks that the two agree.
- `atom.py`: `CrackAtomRecord`, the column layout of the raw dump
  attachments (not uploaded as a table).

## Usage

```python
sim = CrackSimulation(**damage, runId=run_id, campaign=campaign)
frames = frames_table(damage, run_id=run_id)
validate_simulation(sim, frames)
```

Aliases map camelCase fields to the snake_case keys in `damage.json` and the
SNAKE_CASE keys in `parameters.env`. `CrackSimulation` and `CrackVerdict`
ignore unmodeled keys, so a raw `damage.json` validates as-is; all other
models forbid them.

## Notes

- Units follow LAMMPS `units metal` (K, bar, ps, Angstrom) and are given in
  field descriptions.
- Fields with physically meaningful outliers are unbounded: `peMedian`,
  `dLx`/`dLy`/`dVolume`, and the per-atom energy and stress.
- Float cross-checks use `rel_tol=1e-4`, since MPContribs stores 6
  significant digits.
