#!/usr/bin/env sh
# Tears down exactly the buckets + queues that init-aws.sh provisions, and nothing
# else. Names mirror init-aws.sh (and the defaults in src/mpcontribs_api/config.py).
#
# Credential/endpoint handling matches init-aws.sh:
#
#   # MiniStack (default):
#   sh tests/integration/aws/clean-aws.sh
#
#   # Real AWS via a configured profile:
#   AWS_PROFILE=my-profile sh tests/integration/aws/clean-aws.sh
#
# Stays POSIX-compatible (no bash arrays, no `pipefail`) so it can run under the
# same busybox ash as init-aws.sh.
set -eu

# Only the resources init-aws.sh creates. Keep these two lists in sync with it.
BUCKETS="lbnl-msd-bronze lbnl-msd-silver lbnl-msd-gold"
QUEUES="mpcontribs-download mpcontribs-transform mpcontribs-projection"

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

echo "[clean-aws] removing against ${ENDPOINT:-${AWS_PROFILE:+profile $AWS_PROFILE}} ..."

# Empty + delete each bucket. `s3 rb --force` empties non-versioned buckets first.
# `|| true` so a missing bucket (already gone) doesn't abort the rest.
for bucket in $BUCKETS; do
  echo "[clean-aws] bucket ${bucket}"
  aws_local s3 rb "s3://${bucket}" --force || true
done

# Delete each queue by resolving its URL first; skip quietly if it doesn't exist.
for queue in $QUEUES; do
  url=$(aws_local sqs get-queue-url --queue-name "${queue}" --query QueueUrl --output text 2>/dev/null || true)
  if [ -n "$url" ] && [ "$url" != "None" ]; then
    echo "[clean-aws] queue ${queue}"
    aws_local sqs delete-queue --queue-url "$url" || true
  else
    echo "[clean-aws] queue ${queue} (absent)"
  fi
done

echo "[clean-aws] done."
