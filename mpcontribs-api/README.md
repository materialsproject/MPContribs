- https://contribs-api.materialsproject.org
- https://ml-api.materialsproject.org
- https://lightsources-api.materialsproject.org

## Contribution `data`

A contribution's `data` is a hierarchical JSON object (max nesting depth 7). Lists are allowed, and
dictionaries inside them have their keys coerced and validated like any other key. The API applies
two write-time transforms that are important for clients to understand, because **the data you read
back can differ from the data you submitted**.

### Key coercion to `snake_case`

Every dictionary key in `data` is coerced to `snake_case` on write:

- casing is lowercased,
- `camelCase` / `PascalCase` boundaries are split (`bandGap` → `band_gap`),
- any run of spaces, hyphens, or punctuation collapses to a single underscore.

So `"bandGap"`, `"Band Gap"`, and `"band-gap"` are all stored as `"band_gap"`. Keys must be ASCII
and must not reduce to an empty string (e.g. `"***"` is rejected). Colliding keys after coercion
(`"Band Gap"` and `"band_gap"` in the same object) are rejected.

### Annotated keys: units and conditions

A **top-level** key may carry an annotation in parentheses:

```
"name (unit, condition1=value1, condition2=value2, ...)"
```

- The single token without an `=` is the **unit** (`eV`, `S/cm`, `K`, …). Units are stored verbatim
  (not coerced) so they round-trip through [Pint](https://pint.readthedocs.io/).
- Each `k=v` token is a **condition**; condition names are coerced to `snake_case` like other keys.
- `name` may be a dotted path (`"transport.conductivity (S/cm)"`) to nest the value.
- A key with no parentheses is a plain, fully backward-compatible key.

Recognized units are canonicalized to SI base units on write. Magnitudes may carry uncertainty as
`"4.2(3)"`, `"4.2+/-0.3"`, or `"4.2±0.3"`.

A value submitted with a unit annotation is stored as an **annotated leaf**:

| field                       | meaning                                                                      |
| --------------------------- | ---------------------------------------------------------------------------- |
| `value` / `unit`            | SI-canonical form (or submitted form if the unit is unrecognized/dimensionless) |
| `input_value` / `input_unit`| the magnitude and unit exactly as submitted                                  |
| `error`                     | SI-propagated standard deviation (only when an uncertainty was given)        |
| `display`                   | human-readable rendering of the submitted magnitude/unit, e.g. `"4.2+/-0.3 eV"` |

### Pivoting on conditions

If any key carries conditions, a single submitted contribution is **expanded into one contribution
per distinct condition signature**. Each resulting contribution stores its conditions as ordinary
columns, plus its own measurements, plus every condition-less ("broadcast") column, and is stamped
with a server-computed `condition_key` identity. For example:

```jsonc
// submitted
{
  "conductivity (S/cm, T=300K)": 1.2,
  "conductivity (S/cm, T=400K)": 3.4,
  "sample": "A"          // broadcast to every pivoted row
}
// stored: two contributions, one per temperature, each with `t`, `conductivity`, and `sample`
```

Submissions that pivot on conditions may **not** include components (structures/tables/attachments):
insert the pivoted contributions first, then attach components to the rows you want.

**PATCH semantics.** `PATCH /contributions/{id}` runs the same expansion on its `data`:

- Condition-less `data` patches the addressed contribution in place (units are still annotated); its
  `condition_key` is unchanged.
- `data` that carries conditions *fans out*: each condition signature updates the existing pivoted
  row (under the same `project`/`identifier`/`version`) that already has the matching `condition_key`.
  A PATCH never creates new rows or rewrites a `condition_key`, so a signature that matches no stored
  row is rejected. Non-`data` fields on the patch apply to every row it touches. The response is the
  list of updated contributions.

> The write path (key grammar, coercion, and validation) lives in
> `src/mpcontribs_api/domains/_shared/types.py`; expansion/pivoting lives in
> `src/mpcontribs_api/domains/contributions/pivot.py`; unit handling lives in
> `src/mpcontribs_api/domains/_shared/units.py`.
