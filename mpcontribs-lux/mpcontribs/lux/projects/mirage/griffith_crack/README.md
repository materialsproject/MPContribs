# Griffith crack (strain-controlled) Lux schema

Schema for the strain-controlled Griffith-crack LAMMPS workflow in
`MIRAGE_Shared-Examples/examples_pieterjan/cases/griffith/strain_controlled_v2`
of the MIRAGE `lammps` repository. See that directory's `AGENTS.md` for the
full workflow description; this README only covers what's specific to the
MPContribs mapping.

A run machines a notch into a Cu slab, cycles it under oscillatory strain, and
`scripts/metric.py` decides whether the notch-connected void grew
(`crack-growth`) or not (`no-crack-growth`), writing the decision plus
per-frame measurements into that run's `damage.json`.

## Files

- `schema.py` -- `CrackSimulation`, one per `crack.py` run (one MPContribs
  contribution's `data`). Built from a run's `parameters.env` (DOE knobs) and
  `damage.json["verdict"]` (the growth decision + diagnostics). Nested groups:
  `CrackDiagnostics` (the eight non-voting mechanism flags from
  `metric.verdict`) and `EarlyStopInfo` (present only when `crack.py
  --early-stop` killed the run early). `CrackSimulation.from_damage_json(...)`
  builds an instance directly from a parsed `damage.json`.
- `frame.py` -- `CrackFrame`, one row per dumped frame (`damage.json["frames"]`):
  the baseline frame plus every dump in the analyzed window, not only
  cycle-end frames. This is the table meant to accompany a `CrackSimulation`
  contribution. `frames_table(damage, run_id=...)` builds the table directly
  from a parsed `damage.json`; `validate_simulation(sim, frames)` checks the
  cross-table invariants `metric.py` guarantees by construction (one baseline
  row matching `aYBaselineAngstrom`, `nCyclesObserved` matching the row count
  with `cycle is not None`, consistent `runId`, increasing `timestepId`).
- `atom.py` -- `CrackAtomRecord` documents the raw per-atom dump column format
  (`dump.<step>.cracked`: `id type x y z c_6 c_7[1] c_7[2] c_7[3]`) for
  reference. **Not uploaded as an MPContribs table** -- a run analyzes on the
  order of ten to twenty frames at ~750k atoms each, which is both impractical
  as queryable columnar data and redundant with `CrackFrame`. The raw dumps go
  up as MPContribs Attachments instead.

## Units

Follows the LAMMPS `units metal` convention used by the workflow's templates:
K for temperature, **bar** for pressure (not atm -- run-directory names like
`prep_-35746.8atm_...` are a historical naming artifact, not the actual unit),
ps for time, Angstrom for length, radians for angle. Per-atom stress
(`atom.py`) is a pressure*volume quantity (`compute stress/atom`'s native
output), i.e. bar*Angstrom^3, not bar.

## Known provenance gaps (not papered over here)

- `templateVariant` / `backend` are only recorded in `parameters.env` for a
  subset of campaigns (`runs/3_exclusion_ablation`, `runs/4_cpu_benchmark`,
  `runs/00_parameter_scan`); most of the historical corpus leaves them
  unrecorded. `CrackSimulation` leaves these fields `None` rather than
  guessing from the campaign name, since template identity materially changes
  what a run means (see the workflow `AGENTS.md`'s many "not poolable"
  caveats) and silently inferring it risks getting it wrong on a resubmitted
  or hand-run sample.
- `lxAngstrom`/`lyAngstrom`/`lzAngstrom` on `CrackFrame` are the orthogonal box
  edge lengths only. The LAMMPS dump header is triclinic (`xy xz yz` tilt
  factors), but `scripts/metric.py` does not retain the tilt per frame, so a
  full cell reconstruction is not possible from this table alone -- that's a
  property of the upstream data.
- `cna` is null on the large majority of frames; CNA is diagnostic-only and
  not computed by default (see `scripts/metric.py`'s mechanism catalogue).

## Validation

Both models were validated end to end against a real run,
`runs/01_bernoulli_lse_2D/lse_b000_m0_ip_m35746p8_t494p393` (a copy of its
`damage.json` and `parameters.env` lives in
`test_data/by_user/mirage/griffith_crack/damage_sample.json` /
`parameters_sample.env` -- the latter is kept alongside for reference even
though `from_damage_json` only reads the `parameters` block `metric.py`
already copies into `damage.json`), via
`tests/projects/mirage/griffith_crack/test_griffith_crack_schemas.py`, and
against `tests/test_models_for_arrow_compatibility.py`.
