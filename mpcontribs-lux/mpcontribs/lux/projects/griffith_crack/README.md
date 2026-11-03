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
  row matching `aYBaseline`, `nCyclesObserved` matching the row count with
  `cycle is not None`, consistent `runId`, increasing `timestepId`). Its
  nested `CnaFractions` model requires its five fields to sum to ~1 (they are
  always populated together by `metric.py`, never partially -- see the
  docstring).
- `atom.py` -- `CrackAtomRecord` documents the raw per-atom dump column format
  (`dump.<step>.cracked`: `id type x y z c_6 c_7[1] c_7[2] c_7[3]`) for
  reference. **Not uploaded as an MPContribs table**: a run analyzes on the
  order of ten to twenty frames at ~750k atoms each, which is impractical as
  queryable columnar data, and every `CrackFrame` field is already the
  specific aggregate `metric.py` derives from that per-atom data for the
  labelling pipeline -- see the module docstring for the precise claim. The
  raw dumps go up as MPContribs Attachments instead.

## Field naming and units

Field names deliberately carry no unit suffixes (e.g. `temperature`, not
`temperatureK`) -- MPContribs attaches/infers units separately during upload
(the client's `init_columns`, or units inferred from the uploaded value).
Units live only in each field's `description`, and follow the LAMMPS
`units metal` convention used by the workflow's templates: K for temperature,
**bar** for pressure (not atm -- run-directory names like
`prep_-35746.8atm_...` are a historical naming artifact, not the actual unit),
ps for time, Angstrom for length, radians for angle. Per-atom stress
(`atom.py`) is a pressure*volume quantity (`compute stress/atom`'s native
output), i.e. bar*Angstrom^3, not bar.

## Bounds

Most numeric/string fields carry `ge`/`le`/`gt`/`lt`/`max_length`/`pattern`
constraints. Two different kinds are mixed in deliberately:

- **Structural bounds**, read off what `scripts/metric.py`'s code guarantees
  by construction (e.g. fractions in `[0, 1]`, lengths/areas `>= 0`,
  `randSeed{1,2,3}` in `[0, 32767]` exactly matching `crack.py`'s
  `random.randint(0, 32767)`).
- **Generous sanity envelopes** on DOE physical parameters (`temperature`,
  `normalPrestress`, `inPlanePrestress`, `strainAmplitude`, `thetaA`, ...)
  that are several times wider than every value seen in the corpus so far, on
  purpose: they're meant to catch garbage/corrupted input, not to encode the
  current campaigns' sweep ranges, which should stay free to grow without a
  schema change.

A few fields are **deliberately left unbounded**: `CrackFrame.peMedian`,
`CrackAtomRecord.potentialEnergy`/`stress*`, and
`CrackDiagnostics.dLx`/`dLy`/`dVolume`. The corpus contains genuine, meaningful
outliers in these fields -- e.g. 55 known-corrupted runs with per-atom
energies around +1.3e4 eV, and `metric.py` treats a cell volume exceeding 10x
baseline ("cell exploded") as strong positive crack-growth evidence, not as
data to reject. Bounding these would silently discard real corpus data.

## Known provenance gaps (not papered over here)

- `templateVariant` / `backend` are only recorded in `parameters.env` for a
  subset of campaigns (`runs/3_exclusion_ablation`, `runs/4_cpu_benchmark`,
  `runs/00_parameter_scan`); most of the historical corpus leaves them
  unrecorded. `CrackSimulation` leaves these fields `None` rather than
  guessing from the campaign name, since template identity materially changes
  what a run means (see the workflow `AGENTS.md`'s many "not poolable"
  caveats) and silently inferring it risks getting it wrong on a resubmitted
  or hand-run sample.
- `lx`/`ly`/`lz` on `CrackFrame` are the orthogonal box edge lengths only. The
  LAMMPS dump header is triclinic (`xy xz yz` tilt factors), but
  `scripts/metric.py` does not retain the tilt per frame, so a full cell
  reconstruction is not possible from this table alone -- that's a property
  of the upstream data.
- `cna` is null on the large majority of frames; CNA is diagnostic-only and
  not computed by default (see `scripts/metric.py`'s mechanism catalogue).
- `interatomicPotential` on `CrackSimulation` identifies and cites the EAM
  potential (`Cu_mishin1.eam.alloy`; Mishin, Phys. Rev. B 63, 224106 (2001)),
  static across every run in this workflow. It is a small string field, not
  the ~700 KB potential file itself -- whether/how that file is uploaded once
  as a shared reference Attachment (rather than duplicated per contribution)
  is an upload-pipeline decision, not a schema one.

## Validation

Both models were validated end to end against a real run,
`runs/01_bernoulli_lse_2D/lse_b000_m0_ip_m35746p8_t494p393` (a copy of its
`damage.json` and `parameters.env` lives in
`test_data/by_user/griffith_crack/damage_sample.json` / `parameters_sample.env`,
with the absolute `$PSCRATCH` path in `damage_sample.json`'s `run_dir` masked
down to the `runs/...` suffix), via
`tests/projects/griffith_crack/test_griffith_crack_schemas.py`, and against
`tests/test_models_for_arrow_compatibility.py`.
