# Griffith crack (strain-controlled)

LAMMPS simulations of a notched metal slab under cyclic strain. `metric.py`
decides whether the notch grew and writes the result to each run's
`damage.json`.

Each contribution's `identifier` is the mp-id of the simulated material
(`mp-30`, FCC Cu, for the current data); `data.runId` is the unique per-run
key.

## Models

- `schema.py`: `CrackSimulation`, one per run (the contribution's `data`),
  with nested `params` (physical inputs), `provenance` (sample/batch ids,
  seeds, template, backend), `grid`, `verdict` (with `diagnostics`),
  `earlyStop` and `truncated`.
- `frame.py`: `CrackFrame`, one table row per analyzed frame.
  `validate_simulation(sim, frames)` checks that the two agree.
- `atom.py`: `CrackAtomRecord`, the column layout of the raw dump
  attachments (not uploaded as a table).

## Usage

```python
sim = CrackSimulation(
    **damage, runId=run_id, campaign=campaign, interatomicPotential=potential
)
frames = frames_table(damage, run_id=run_id)
validate_simulation(sim, frames)
```

Aliases map camelCase fields to the snake_case keys in `damage.json` and the
SNAKE_CASE keys in `parameters.env`; the `parameters` block is split into
`params` and `provenance` on input. `runId`, `campaign` and
`interatomicPotential` are not in `damage.json` and must be passed in.
`CrackSimulation` and `CrackVerdict` ignore unmodeled keys, so a raw
`damage.json` validates as-is; all other models forbid them. Only
`damage.json` version 2 is accepted.

## Notes

- Units follow LAMMPS `units metal` (K, bar, ps, Angstrom) and are given in
  field descriptions.
- Numeric bounds are only those known to hold (e.g. positive lengths,
  fractions in [0, 1], seeds in [0, 32767]); sweep ranges such as
  temperature, prestress and cycle count are not capped.
- Float cross-checks use `rel_tol=1e-4`, since MPContribs stores 6
  significant digits.
