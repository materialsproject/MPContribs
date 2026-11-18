# Griffith crack

LAMMPS simulations of a notched metal slab under cyclic load.

Each contribution's `identifier` is the mp-id of the simulated material
(for example `mp-30`, FCC Cu). Simulation `data.runId` is the unique per-run
key.

## Models

- `schema.py`: `CrackSimulation`, one per run,
  with nested `params` (physical inputs), `provenance` (sample/batch ids,
  seeds, template), `grid`, `verdict` (with `diagnostics`),
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

The `parameters` block is split into
`params` and `provenance` on input. `runId`, `campaign` and
`interatomicPotential` are not in the simulation output file (`damage.json`) and must be passed in.
`CrackSimulation` and `CrackVerdict` both ignore unmodeled keys.

## Notes

- Units follow LAMMPS `units metal` (K, bar, ps, Angstrom) and are given in
  field descriptions.
- Numeric bounds are only those known to hold (e.g. positive lengths,
  fractions in [0, 1]).
- Float cross-checks use `rel_tol=1e-4`, since MPContribs stores 6
  significant digits.
