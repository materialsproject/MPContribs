# Updating information

How to change data that is already in MPContribs — a project's metadata, or a contribution's fields —
after it has been materialized.

Everything is **S3-first**: you never write to the database directly. You open an upload session,
PUT your change into S3, and complete the session; an out-of-repo transform worker then reflects the
change into MongoDB. This is the same pipeline used to create data (see `docs/user-upload-flow.d2`),
with a different session `operation`.

## Two ways to change something

| `operation` | Means | Applies to |
|-------------|-------|------------|
| `replace`   | Overwrite the whole object at the file's location | project, contributions, components |
| `update`    | Merge only the named fields into what's already there | project, contributions |

- **`replace`** takes a complete object. A whole `project.json`, a whole contributions file (each row a
  complete contribution, matched by identity), or a whole component file (CIF/parquet/image). Any format
  the role allows (CSV included).
- **`update`** takes a *partial*. It merges the fields you name and leaves everything else untouched.
  Because a partial must distinguish "unchanged" from "set to null", `update` files must be **JSON or
  JSONL** — CSV is rejected at session initiate (a blank cell is ambiguous).
- **Components have no fields to merge** (a CIF is an opaque blob), so they are `replace`-only. `update`
  does not accept the `component` role.

The rest of this doc is about `update`. (`replace` is just "upload the whole thing again.")

## The update envelope

Every `update` record is the same shape — the **standard form for any update**:

```json
{ "identity": { <composite key of the thing to change> },
  "update":   { <field path>: <new value>, ... } }
```

- **`identity`** locates an existing resource. It is never mutated — it is only used to find the row.
- **`update`** is a **flat map of dotted field paths to new values**, applied as a `$set`-style merge:
  - `"data.bandgap": 1.2` sets exactly that leaf and leaves its siblings in `data` alone.
  - `"is_public": true` sets a top-level field.
  - `"data.notes": null` **clears** a field.
- **To change an identity field**, put its new value in `update`; the record is still located by the
  *old* `identity`. (See [Re-keying](#re-keying-a-contribution).)

## Getting a contribution's identity

You don't construct the key by hand — **you already have it from reading the contribution.** Every read
returns the full identity in its response (`ContributionOut`):

- `GET /api/v1/contributions/{id}`
- `GET /api/v1/contributions/item?project=...&chemical_system_id=...` (address by composite key)
- `GET /api/v1/contributions/search` / `GET /api/v1/contributions?...`

The identity fields (declaration order = index order):

| field | required | who sets it |
|-------|----------|-------------|
| `project` | yes | you |
| `material_id` | no | you |
| `chemical_system_id` | yes | you |
| `formula` | conditional | you |
| `unique_value` | no | **derived** from `data[<project.unique_column>]` |
| `condition_key` | no | **server-owned** (pivoting) |

Identifier **specificity hierarchy**: `chemical_system_id` > `formula` > `material_id` —
`chemical_system_id` is always required, and `formula` is required whenever `material_id` is set.

Copy the whole `identity` block from the read response verbatim into your update record — including the
derived/server fields (`unique_value`, `condition_key`) — so the worker matches the exact contribution.

## What you can update on a contribution

**Allowed:** `data.*` (any data leaf), `material_id` / `chemical_system_id` / `formula` (an identity
re-key), `is_public`.

**Not allowed:** `project` (moving a contribution between projects is not an update), `unique_value`
(it's derived — change it by updating the `data` field at the project's `unique_column` path and the
server re-derives it), `condition_key` / `_id` / `last_modified` (server-owned), and the
`structures` / `tables` / `attachments` reference lists (manage components by uploading them).

## End to end: fix one field

A user finds `bandgap` is wrong on one contribution and no longer has their source CSV.

1. **Read it** to get the identity:
   `GET /api/v1/contributions/{id}` → copy the `identity` block from the response.
2. **Build a one-line JSONL** `contrib_updates.jsonl`:
   ```
   {"identity":{"project":"solar_cells","chemical_system_id":"Si-O","formula":"SiO2","material_id":"mp-149","unique_value":"sample-7","condition_key":""},"update":{"data.bandgap":1.2}}
   ```
3. **Initiate the session** — `POST /api/v1/uploads`:
   ```json
   { "project": "solar_cells", "operation": "update",
     "files": [ { "filename": "contrib_updates.jsonl", "role": "contributions",
                  "format": "jsonl", "content_type": "application/x-ndjson", "size": 180 } ] }
   ```
   The response carries a presigned PUT URL for the file.
4. **PUT the file body** to that URL (the bytes never pass through the API).
5. **Complete** — `POST /api/v1/uploads/{id}/complete` — which enqueues the session for the worker.
6. The **worker** reads the JSONL, locates the contribution by `identity`, and merges `data.bandgap`.

**Batching:** put one record per line — a single JSONL file (one PUT) can carry thousands of
independent contribution updates.

## Re-keying a contribution

To correct an identity field, locate by the old key and supply the new value under `update`:

```
{"identity":{"project":"solar_cells","chemical_system_id":"Si-O","formula":"SiO2","material_id":"mp-149","unique_value":"sample-7","condition_key":""},"update":{"formula":"SiO3"}}
```

The worker re-validates the hierarchy, rejects a new identity that collides with a different existing
contribution, and re-derives `unique_value` if you changed the `data` field at the project's
`unique_column` path.

## Updating project metadata

Same envelope, one record, in a `project`-role JSON file (`format: "json"`). `identity` is just the
project id; the id itself cannot change.

```json
{ "identity": { "project": "solar_cells" },
  "update":   { "title": "Updated title", "other.doi": "10.1234/abcd" } }
```

## Deleting

Deletions are **not** an `update`. Clearing a *field* is fine (set it to `null` in `update`); removing a
*contribution* is a separate, explicit operation (so a partial upload can never delete rows by omission).
