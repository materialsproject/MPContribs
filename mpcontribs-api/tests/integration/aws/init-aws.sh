#!/usr/bin/env sh
# Provisions the buckets + queues the app expects.
#
# Runs automatically INSIDE the MiniStack container as a ready.d hook (mounted into
# /docker-entrypoint-initaws.d/ready.d/), where MiniStack pre-populates AWS_ENDPOINT_URL
# and test credentials. MiniStack's runner executes ready scripts with POSIX `sh`
# (Alpine busybox ash), ignoring the shebang, so this script stays POSIX-compatible:
# no bash arrays, no `pipefail`. It's also safe to run from the host:
#
#   sh tests/integration/aws/init-aws.sh
#
# MiniStack ships no `awslocal`; we call the standard aws CLI with an explicit endpoint.
# Names mirror the defaults in src/mpcontribs_api/config.py (S3Settings / SqsSettings) and
# must stay in sync with env.aws.example.
set -eu

ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

# POSIX-sh stand-in for a bash array: prefix every call with the endpoint flag.
aws_local() {
  aws --endpoint-url "$ENDPOINT" "$@"
}

echo "[init-aws] provisioning against ${ENDPOINT} ..."

# --- S3 buckets (S3Settings: staging_bucket / raw_data_bucket / processed_data_bucket / blobs_bucket) ---
for bucket in mpcontribs-staging mpcontribs-raw mpcontribs-processed mpcontribs-blobs; do
  aws_local s3 mb "s3://${bucket}" || true
done

# Users upload into the staging bucket, so browser-based presigned PUT/POST needs CORS there
# (no-op/harmless for curl & python clients).
aws_local s3api put-bucket-cors --bucket mpcontribs-staging --cors-configuration '{
  "CORSRules": [{
    "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
    "AllowedOrigins": ["*"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"]
  }]
}'

# --- SQS queues (the three the app enqueues to) ---
for queue in mpcontribs-download mpcontribs-transform mpcontribs-projection; do
  aws_local sqs create-queue --queue-name "${queue}" || true
done

echo "[init-aws] done."
echo "[init-aws] buckets:" && aws_local s3 ls
echo "[init-aws] queues:" && aws_local sqs list-queues
