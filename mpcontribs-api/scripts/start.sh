#!/bin/bash

set -e
zzz=$((DEPLOYMENT * 60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

PMGRC=$HOME/.pmgrc.yaml
[[ ! -e "$PMGRC" ]] && echo "PMG_DUMMY_VAR: dummy" >"$PMGRC"

STATS_ARG=""
SERVER_APP="mpcontribs.api:create_app()"
WAIT_FOR="wait-for-it.sh $JUPYTER_GATEWAY_HOST -q -t 50"

set -x

if [[ -n "$DD_TRACE_HOST" ]]; then
  wait-for-it.sh "$DD_TRACE_HOST" -q -s -t 10 && STATS_ARG="--statsd-host $DD_AGENT_HOST:8125" || echo "WARNING: datadog agent unreachable"
fi

[[ -n "$STATS_ARG" ]] && CMD="ddtrace-run" || CMD=""
exec $WAIT_FOR -- $CMD gunicorn $STATS_ARG $SERVER_APP
