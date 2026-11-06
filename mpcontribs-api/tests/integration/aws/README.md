# AWS integration tests (S3 + SQS uploads)

End-to-end tests for the uploads flow (`src/mpcontribs_api/domains/uploads/`) that drive the real
FastAPI app against real S3 + SQS and a real MongoDB. The same tests run against two targets, selected
by `MPCONTRIBS_TEST_AWS_TARGET`:

- **`ministack`** (default): a throwaway AWS cloud on your laptop (no AWS creds needed).
- **`cloud`**: a real **cloud dev AWS account + dev MongoDB cluster** (the "full dev test").

What they verify (no worker runs — the graduated silver/gold buckets are not checked):

- objects land in the **bronze** bucket (`lbnl-msd-bronze`): per-upload role files under
  `mpcontribs/{project}/{seq}/` (canonical `project.json` / `contributions.{ext}`), and components at
  the shared, content-addressed `mpcontribs/{project}/components/{kind}s/{sha256}.{ext}`,
- the Mongo `uploads` doc moves `pending → completed` (a `delete` is a one-shot `completed`),
- completion writes `manifest.json` (operation + timestamp + authz + per-file descriptors; a `delete`
  also writes `deletions.json`),
- completion enqueues exactly one `{bucket, manifest_key}` message on a **dedicated test transform
  queue** (`mpcontribs-transform-test`, so the shared queue / any live worker is never disturbed).

Components (and single-PUT role files) declare a real `sha256`, exercising the production integrity
path (the bound content hash on single PUTs, and the content address of components). The large
`contributions.csv` is the one multipart vehicle and uses plain multipart (no declared hash) to stay
portable across MiniStack and real S3 — a multipart component would force the FULL_OBJECT checksum
path MiniStack rejects, which is why components are kept single-shot here.

---

## Target A — MiniStack (local, default)

Docs: <https://ministack.org/docs/configuration>

### Prerequisites
- Docker (with `docker compose`)
- The `aws` CLI on your host (for provisioning / the manual walkthrough)

### Start it
```bash
cd tests/integration/aws
docker compose up --wait        # boots MiniStack and runs init-aws.sh in ready.d
bash init-aws.sh                # safety net if the in-container hook can't run (e.g. no aws CLI)
```

`init-aws.sh` provisions, to match `config.py`:
- **Buckets:** `lbnl-msd-bronze`, `lbnl-msd-silver`, `lbnl-msd-gold` (CORS on bronze)
- **Queues:** `mpcontribs-download`, `mpcontribs-transform`, `mpcontribs-projection`

The test harness additionally check-and-creates anything still missing (including the
`mpcontribs-transform-test` queue), so a bare `docker compose up --wait` is enough in practice.

### Run
```bash
uv run pytest tests/integration/aws -q -s
```
The suite self-skips if MiniStack or MongoDB is unreachable. `KEEP_ARTIFACTS=1` leaves this run's
bronze objects, Mongo doc, and transform message in place (the per-run `mpcontribs/{project}/…` prefix
is printed with `-s`); each run uses a fresh random project id, so kept artifacts never collide.

### Verify / inspect
```bash
curl -s http://localhost:4566/_ministack/health
aws --endpoint-url http://localhost:4566 s3 ls s3://lbnl-msd-bronze --recursive
aws --endpoint-url http://localhost:4566 sqs list-queues
```

### Reset / tear down
```bash
curl -sX POST http://localhost:4566/_ministack/reset   # wipe state, keep container running
docker compose down                                    # stop (state persists in ./volume)
rm -rf volume                                          # wipe persisted buckets/queues on disk
```

---

## Target B — cloud dev AWS + dev MongoDB (the full dev test)

Runs the identical tests against a real dev AWS account and dev Atlas cluster. The harness touches
**nothing** about the endpoint/region/credentials/Mongo — it inherits them from your dev environment,
and (per `app.py`) an empty `MPCONTRIBS_AWS__ENDPOINT_URL` resolves to the region's default AWS
endpoints.

1. **Provision the dev account** (buckets + queues) — reuse `init-aws.sh` with an AWS profile:
   ```bash
   AWS_PROFILE=<dev-profile> bash tests/integration/aws/init-aws.sh
   ```
   The harness also check-and-creates anything missing, and always creates the dedicated
   `mpcontribs-transform-test` queue it asserts against.

2. **Point the app at dev** — in your `.env` (or exported env):
   ```bash
   MPCONTRIBS_MONGO__URI=<dev atlas uri>
   MPCONTRIBS_MONGO__DB_NAME=<dev db>
   MPCONTRIBS_AWS__REGION=<region>          # defaults to us-east-1 if unset
   # Leave MPCONTRIBS_AWS__ENDPOINT_URL EMPTY for the region's default AWS endpoints (set it only if
   # the dev account needs a non-default endpoint). A leftover localhost value here silently keeps the
   # run on MiniStack.
   ```

3. **Provide credentials boto can read.** The app and tests use boto3/botocore, which only read
   *standard* credential sources (env vars, static keys in `~/.aws/credentials`, `sso`,
   `credential_process`, instance role). If your profile uses a CLI-only mechanism (e.g. a
   `login_session` key, or an SSO session boto can't see), `AWS_PROFILE=<name>` alone yields
   "Unable to locate credentials". Materialize the profile's creds as env vars first:
   ```bash
   eval "$(aws configure export-credentials --profile <name> --format env)"
   ```

4. **Run:**
   ```bash
   MPCONTRIBS_TEST_AWS_TARGET=cloud uv run pytest tests/integration/aws -q -s
   ```
   Skips with a clear message (including the export-credentials hint) if credentials/region are missing
   or Mongo is unreachable.

Notes:
- The tests only create/read the per-run `mpcontribs/{project}/…` prefix and the dedicated test queue;
  they never drain the shared `mpcontribs-transform` queue. Teardown wipes only this run's prefix,
  `uploads` doc, and test-queue messages (`KEEP_ARTIFACTS=1` to skip teardown).
- The bronze/silver/gold buckets are institution-owned and shared — the harness is idempotent and will
  not recreate or mutate them beyond best-effort CORS.

---

## Manual walkthrough (uploads flow)

The authoritative, runnable example is `test_s3_upload.py`. The shape of the flow:

```
# 1. initiate — POST a manifest of {type, name, size_bytes, subtype?, sha256} files
#    (components require sha256; a `delete` POSTs {operation: delete, deletions:{...}} and no files)
#    -> 201 {id, seq, operation, project, status, files:[{name, key, type, status, num_parts, part_size, url}]}
POST /api/v1/uploads   (+ auth headers)

# 2. transfer — single files: PUT bytes to the presigned url (send Content-Type + x-amz-checksum-sha256);
#    multipart files: POST .../files/parts {key, start_part} for part urls, PUT each part, collect ETags.
#    (a file is identified by its resolved object `key` from the initiate response — names aren't unique)

# 3. complete — POST .../{id}/complete {files:[{key, parts:[{part_number, etag}]}]}
#    -> flips the uploads doc to "completed", writes manifest.json, enqueues the transform message.
```

Inspect what landed (uploads stage in bronze before the worker graduates them to silver/gold):
```bash
E=http://localhost:4566
aws --endpoint-url $E s3 ls s3://lbnl-msd-bronze/mpcontribs/ --recursive
aws --endpoint-url $E sqs receive-message --queue-url $E/000000000000/mpcontribs-transform-test
```

---

## Notes
- MiniStack persistence is on (`PERSIST_STATE=1`, `S3_PERSIST=1`); state lives under `./volume`
  (gitignored). Turn both off in the compose file for clean, deterministic CI runs.
- Presigned URLs resolve to `http://localhost:4566/...` under MiniStack, so they only work from the
  host. If you run the app *inside* a container on the compose network, it must reach MiniStack by
  service name — but the presigned URLs it hands a host client still need `localhost` (set
  `MINISTACK_HOST`).
- The slim image here covers S3 + SQS. Lambda/other optional services need the `:full` image.
