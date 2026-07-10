# Client-facing documentation for the Contribution ``data`` field. Referenced as the OpenAPI schema
# description on the input/output models (see ``contributions.models``) so it renders in the docs UI
# and generated clients. Keep these in sync with the behavior in ``contributions.pivot`` and
# ``_shared.units``.

CONTRIBUTION_DATA_INPUT_DESCRIPTION = """\
Hierarchical, JSON-object data for the contribution. Nesting deeper than 7 levels is rejected. Lists
are allowed; any dictionaries inside them have their keys coerced and validated like every other key.

**Key coercion (important):** every dictionary key is coerced to `snake_case` on write. Casing is
lowercased, `camelCase`/`PascalCase` boundaries are split, and any run of spaces/hyphens/punctuation
collapses to a single underscore. So `"bandGap"`, `"Band Gap"`, and `"band-gap"` are all stored as
`"band_gap"`, and the **keys you read back may differ from the keys you submitted**. Keys must be
ASCII and must not reduce to an empty string (e.g. `"***"` is rejected).

**Annotated keys (units + conditions):** a top-level key may carry an annotation in parentheses:

    "name (unit, condition1=value1, condition2=value2, ...)"

- The single token without an `=` is the **unit** (e.g. `eV`, `S/cm`, `K`); units are left verbatim
  (not coerced) so they round-trip through Pint.
- Each `k=v` token is a **condition**. Condition names are coerced to `snake_case` like any other key.
- The `name` may be a dotted path (`"transport.conductivity (S/cm)"`) to nest the value.
- A key with no parentheses is a plain, fully backward-compatible key.

Recognized units are canonicalized to SI base units on write (the submitted form is preserved too —
see the response schema). Magnitudes may carry uncertainty as `"4.2(3)"`, `"4.2+/-0.3"`, or
`"4.2±0.3"`.

**Pivoting on conditions:** if any key carries conditions, the single submission is *expanded* into
one contribution per distinct condition signature. Each resulting contribution stores its conditions
as ordinary columns plus its own measurements plus every condition-less ("broadcast") column, and
gets a server-computed `condition_key` identity. Submissions that pivot on conditions may **not**
include components (structures/tables/attachments) — insert the pivoted contributions first, then
attach components.

**On PATCH:** the same expansion runs. Condition-less data patches the addressed contribution in
place (units still annotated). Data carrying conditions *fans out*: each signature updates the
existing pivoted row that already has the matching `condition_key` (a PATCH never creates rows or
changes a row's `condition_key`), so a signature with no matching stored row is rejected.
"""

CONTRIBUTION_DATA_OUTPUT_DESCRIPTION = """\
Hierarchical contribution data. Keys are stored in `snake_case` (see the write schema for the
coercion rules), so they may differ from the keys originally submitted.

Values that were submitted with a unit annotation are stored as an **annotated leaf** object:

- `value` / `unit`: the SI-canonical magnitude and unit (or the submitted form when the unit is
  unrecognized or dimensionless)
- `input_value` / `input_unit`: the magnitude and unit exactly as submitted
- `error`: the (SI-propagated) standard deviation — present only when the magnitude carried an
  uncertainty
- `display`: a human-readable rendering of the *submitted* magnitude/unit (e.g. `"4.2+/-0.3 eV"`)

Plain (unannotated) values keep whatever JSON shape they were submitted with.
"""

openapi_tags = [
    {
        "name": "projects",
        "description": "contain provenance information about contributed datasets. Deleting projects will also delete "
        "all contributions including tables, structures, attachments, notebooks and cards for the project. Only users "
        "who have been added to a project can update its contents. While unpublished, only users on the project can "
        "retrieve its data or view it on the Portal. Making a project public does not automatically publish all its "
        "contributions, tables, attachments, and structures. These are separately set to public individually or in "
        "bulk.",
    },
    {
        "name": "contributions",
        "description": "contain simple hierarchical data which will show up as cards on the MP details page for MP "
        "material(s). Tables (rows and columns), structures, and attachments can be added to a contribution. "
        "Each contribution uses `mp-id` or composition as identifier to associate its data with the according entries "
        "on MP. Only admins or users on the project can create, update or delete contributions, and while unpublished, "
        "retrieve its data or view it on the Portal. Contribution components (tables, structures, and attachments) are "
        "deleted along with a contribution. **Note:** `data` keys are coerced to `snake_case` on write and may carry "
        "unit/condition annotations of the form `name (unit, cond=value, ...)`; keys with conditions cause the "
        "submission to pivot into one contribution per condition signature. See the `data` field on the request and "
        "response schemas for the full grammar and the annotated-value shape.",
    },
    {
        "name": "structures",
        "description": "are [pymatgen structures](https://pymatgen.org/pymatgen.electronic_structure.html) which can "
        " be added to a contribution.",
    },
    {
        "name": "tables",
        "description": "are simple spreadsheet-type tables with columns and rows saved as "
        "[Polars DataFrames](https://docs.pola.rs/api/python/stable/reference/dataframe/index.html) which can be added "
        "to a contribution.",
    },
    {
        "name": "attachments",
        "description": "are files saved as objects in AWS S3 and not accessible for querying (only retrieval) which "
        "can be added to a contribution.",
    },
]

contact_info = {
    "name": "MPContribs",
    "url": "https://mpcontribs.org/",
    "email": "contribs@materialsproject.org",
}

license_info = {
    "name": "Creative Commons Attribution 4.0 International License",
    "url": "https://creativecommons.org/licenses/by/4.0/",
}
