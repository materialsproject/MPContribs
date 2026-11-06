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

# When AWS_PROFILE is set, use that profile's credentials/region/endpoint and
# target real AWS (no forced test creds, no implicit localhost endpoint). An
# endpoint is only added if you explicitly export AWS_ENDPOINT_URL.
#
#   AWS_PROFILE=my-profile sh tests/integration/aws/init-aws.sh
#
# With no profile, behave exactly as before: default to MiniStack with dummy creds.
PROFILE_FLAG=""
if [ -n "${AWS_PROFILE:-}" ]; then
  PROFILE_FLAG="--profile ${AWS_PROFILE}"
  ENDPOINT="${AWS_ENDPOINT_URL:-}"
  # Respect the profile's own region; only honor AWS_DEFAULT_REGION if explicitly set.
else
  ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
  export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
  export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
  export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
fi

# POSIX-sh stand-in for a bash array: prefix every call with the profile and,
# when set, the endpoint flag.
aws_local() {
  if [ -n "$ENDPOINT" ]; then
    aws $PROFILE_FLAG --endpoint-url "$ENDPOINT" "$@"
  else
    aws $PROFILE_FLAG "$@"
  fi
}

echo "[init-aws] provisioning against ${ENDPOINT:-${AWS_PROFILE:+profile $AWS_PROFILE}} ..."

# Create S3 buckets in aws environment
for bucket in lbnl-msd-bronze lbnl-msd-silver lbnl-msd-gold; do
  aws_local s3 mb "s3://${bucket}" || true
done

# Users upload into the bronze bucket, so browser-based presigned PUT/POST needs CORS there
# (no-op/harmless for curl & python clients). Only applied in the MiniStack (no-profile)
# path: the wildcard origin is fine for a throwaway container but shouldn't be pushed onto
# a real bucket in a real account. Configure CORS explicitly for real deployments instead.
if [ -z "$PROFILE_FLAG" ]; then
  aws_local s3api put-bucket-cors --bucket lbnl-msd-bronze --cors-configuration '{
    "CORSRules": [{
      "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
      "AllowedOrigins": ["*"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"]
    }]
  }'
fi

# SQS queues
for queue in mpcontribs-download mpcontribs-transform mpcontribs-projection; do
  aws_local sqs create-queue --queue-name "${queue}" || true
done

echo "[init-aws] done."
echo "[init-aws] buckets:" && aws_local s3 ls
echo "[init-aws] queues:" && aws_local sqs list-queues
