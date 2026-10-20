# Local AWS (S3 + SQS) via MiniStack

A throwaway AWS cloud on your laptop so you can drive the real uploads flow
(`src/mpcontribs_api/domains/uploads/`) against live S3 + SQS without AWS creds.

Docs: <https://ministack.org/docs/configuration>

## Prerequisites

- Docker (with `docker compose`)
- The `aws` CLI on your host (for the manual walkthrough / host-side provisioning)

## Start it

```bash
cd tests/integration/aws
docker compose up --wait        # boots MiniStack and runs init-aws.sh in ready.d
```

`init-aws.sh` provisions, to match `config.py`:

- **Buckets:** `mpcontribs-staging`, `mpcontribs-raw`, `mpcontribs-processed`, `mpcontribs-blobs`
- **Queues:** `mpcontribs-download`, `mpcontribs-transform`, `mpcontribs-projection`

If the in-container hook can't run (e.g. no `aws` CLI in the image), provision from
the host instead — the same script works either way:

```bash
bash init-aws.sh
```

Verify:

```bash
curl -s http://localhost:4566/_ministack/health                      # service states
aws --endpoint-url http://localhost:4566 s3 ls                       # buckets
aws --endpoint-url http://localhost:4566 sqs list-queues             # queues
```

## Point the app at it

```bash
cp env.aws.example .env.aws
set -a; source .env.aws; set +a    # exports MPCONTRIBS_AWS__* + dummy AWS creds
# ...then run the app from the repo root with these vars in its environment.
```

The key switch is `MPCONTRIBS_AWS__ENDPOINT_URL=http://localhost:4566`, which
`app.py` passes straight to the aioboto3 S3/SQS clients. The dummy
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` only exist so boto will sign requests;
MiniStack ignores their values.

## Play with the uploads flow

```bash
E=http://localhost:4566

# 1. initiate a small upload -> returns {id, url} (a presigned PUT at :4566)
curl -sX POST localhost:8000/api/v1/uploads \
  -H 'Content-Type: application/json' -d '{"size": 1024}'   # + your auth headers

# 2. PUT bytes straight to S3 via the returned presigned url
curl -X PUT --data-binary @somefile "<url from step 1>"

# 3. complete -> flips the doc to "completed" and enqueues an SQS message
curl -sX POST localhost:8000/api/v1/uploads/<id>/complete -d '{}'

# inspect what landed (uploads land in staging before graduation to raw)
aws --endpoint-url $E s3 ls s3://mpcontribs-staging --recursive
aws --endpoint-url $E sqs receive-message \
  --queue-url $E/000000000000/mpcontribs-transform
# or peek via the admin API:
curl -s $E/_ministack/sqs/messages
```

## Reset / tear down

```bash
curl -sX POST http://localhost:4566/_ministack/reset   # wipe state, keep container running
docker compose down                                    # stop (state persists in ./volume)
rm -rf volume                                          # wipe persisted buckets/queues on disk
```

## Notes

- Persistence is on (`PERSIST_STATE=1`, `S3_PERSIST=1`); state lives under `./volume`
  (gitignored). Turn both off in the compose file for clean, deterministic CI runs.
- Presigned URLs resolve to `http://localhost:4566/...`, so they only work from the
  host. If you later run the app *inside* a container on the compose network, it must
  reach MiniStack by service name — but the presigned URLs it hands a browser/host
  client still need to say `localhost` (set `MINISTACK_HOST` accordingly).
- The slim image here covers S3 + SQS. Lambda/other optional services need the
  `:full` image plus the Docker socket and `DOCKER_NETWORK` (see the ministack docs).
