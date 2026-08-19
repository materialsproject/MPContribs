# A_Lab mpcontribs-lux schema — drop-in update

Validated replacement for `mpcontribs-lux/mpcontribs/lux/projects/alab/schemas/`, matching the current A-Lab pipeline's semi-nested contribution model (see `MODEL_SPEC.md` in the main repo).

## Files

- `__init__.py` — package registration, same pattern as the current repo's `schemas/__init__.py`
- `experiments.py` — `Experiment` (top-level summary) + its two nested groups, `HeatingSummary` and `PowderRecoverySummary`
- `sample_preparation.py`, `heating.py`, `powder_recovery.py`, `characterization.py` — one model per attached table
- `timing.py` — `Timing` (`taskCreated`/`taskStarted`/`taskCompleted`, defined once), subclassed as `DoseTiming` in `sample_preparation.py` to add `doseTime`; every table embeds it as a nested `timing` field rather than repeating the three fields inline

`base.py` (`ExcludeFromUpload` etc.) is **not** part of this handoff — MPContribs-Lux doesn't need it. It's still used on the pipeline's own upload side, just not shipped here.

## What changed vs. the schema currently in the repo

- **Table set**: `experiment_elements.py`, `powder_doses.py`, `temperature_logs.py`, `workflow_tasks.py`, `xrd_data_points.py` are gone. The model is now one lean `Experiment` summary + exactly 4 attached-table schemas (`sample_preparation`, `heating`, `powder_recovery`, `characterization`).
- **Field naming**: camelCase throughout (`totalDosedMass`, `xrdTwoTheta`, etc.), not the snake_case in the schemas currently checked into the repo — this follows the MP team's own earlier move to camelCase for the alab schema; these files match that, not the older scaffold.
- **Stage-prefix drop (this update)**: table columns that used to repeat their stage's prefix (`dosingCruciblePosition`, `heatingMethod`, `recoveryInitialCrucibleWeight`, etc.) are now bare (`cruciblePosition`, `method`, `initialCrucibleWeight`). Two fields in the `Heating` table keep a distinguishing suffix instead of going fully bare, because dropping the prefix would collide with that table's own logged reading: `heatingTemperature` → `temperatureTarget` (vs. the table's own logged `temperature`), `heatingTime` → `dwellTime` (vs. the table's own logged `time`) — matched in `HeatingSummary` too, so the summary and table use the identical field name for the same quantity. `Sample preparation`'s `accuracyPercent` → `doseAccuracyPercent` (kept the `Percent` suffix deliberately). `Powder recovery`'s `recoveryYieldPercent` is the one field that keeps its prefix, unlike everything else in that table — a deliberate exception, not an oversight.
- **`Experiment` is lean**: `experimentType`, `experimentSubgroup`, `lastUpdated`, `status` are gone from the top level entirely (privacy/lean pass — they still exist in our internal pipeline snapshot, just not in what's released). Only `heating` (4 fields) and `powderRecovery` (1 field) remain as nested groups; `samplePreparation` and `characterization` no longer exist as top-level groups at all — their full detail lives only on the attached tables now.
- **Timestamps are relative, not absolute**: every table's task timestamps (`taskCreated`/`taskStarted`/`taskCompleted`) and `samplePreparation`'s `doseTime` are hours-since-sample-creation floats, not datetimes — a privacy transform (no absolute dates in the released data). An event that would compute to a negative offset is nulled rather than kept negative.
- **Timing consolidated into one shared class**: `taskCreated`/`taskStarted`/`taskCompleted` used to be redefined inline in each of the 4 table schemas; they're now defined once in `Timing` (`timing.py`) and embedded as a nested `timing` field on every table. `sample_preparation.py`'s extra `doseTime` field is handled by `DoseTiming`, a one-field subclass of `Timing`, embedded there as `timing: DoseTiming`. This is a schema-side-only reorganization — the underlying values, field names, and released data are unchanged.
- **`characterization.xrdFileName`** is the AerisData scan reference, sanitized to `"{rgNumber}.xrdml"` — the original filename (which could embed the raw project/index and a scan date) is not exposed.
- **No embargoed field is modeled anywhere.** `recovery_weight_collected_mg` and `xrd_total_mass_dispensed_mg` are excluded at pipeline extraction — they never reach any parquet table — so there's nothing to mark `ExcludeFromUpload` currently.

## Validation

Every model validated against the **complete** current released dataset (not a sample), 0 errors:

| Model | Rows checked |
|---|---:|
| `Experiment` | 1,149 |
| `SamplePreparation` | 3,327 |
| `Heating` | 507,437 |
| `PowderRecovery` | 1,149 |
| `Characterization` | 11,146,156 |

## Known convention gaps (flagging for review, not resolved here)

- **`heating.setpoints`**: a real column in the underlying parquet table (list-of-dicts, always null in the current release) is deliberately *not* modeled here and is excluded from the actual MPContribs upload by the pipeline's own upload script — a Pydantic `BaseModel, extra="forbid"` can't cleanly represent "present in the table but never uploaded" as a typed field. Flagging in case a structured setpoints schema is wanted later once the field is actually populated.
- **`xrdTwoTheta` naming**: our upload code currently derives this camelCase spelling mechanically (via an explicit override, since "twotheta" has no internal word break to camelCase automatically). Not yet finalized on our end -- open to a different exact spelling if preferred, it's a one-line change on our side.
- **Nested groups vs. flat fields**: `heating` and `powderRecovery` are real nested Pydantic sub-models (matching how MPContribs' own nested `data` dicts work), but every other stage's data (`samplePreparation`'s dosing detail, all of `characterization`'s XRD detail) is *only* on the attached tables, not mirrored at the top level at all. If empty/placeholder nested groups are preferred for symmetry, that's a design call, not a mapping problem on our end.
