#!/bin/bash

set -e
zzz=$((DEPLOYMENT * 60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

CMD="flask rq $1"
set -x

#if [[ -n "$DD_TRACE_HOST" ]]; then
#  wait-for-it.sh "$DD_TRACE_HOST" -q -s -t 10 && CMD="ddtrace-run $CMD" || echo "WARNING: datadog agent unreachable"
#fi

exec wait-for-it.sh "$JUPYTER_GATEWAY_HOST" -q -s -t 50 -- \
  wait-for-it.sh "$MPCONTRIBS_API_HOST" -q -s -t 15 -- $CMD
