#!/bin/bash

set -e
zzz=$((DEPLOYMENT * 60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

PMGRC=$HOME/.pmgrc.yaml
[[ ! -e "$PMGRC" ]] && echo "PMG_DUMMY_VAR: dummy" >"$PMGRC"

set -x

<<<<<< HEAD
exec uvicorn mpcontribs_api.app:app --host 0.0.0.0 --port "$API_PORT" --workers "${NWORKERS:-2}"
||||||| parent of ba089932 (Infra changes for rewrite)
if [[ -n "$DD_TRACE_HOST" ]]; then
  wait-for-it.sh "$DD_TRACE_HOST" -q -s -t 10 && STATS_ARG="--statsd-host $DD_AGENT_HOST:8125" || echo "WARNING: datadog agent unreachable"
fi

[[ -n "$STATS_ARG" ]] && CMD="ddtrace-run gunicorn $STATS_ARG" || CMD="gunicorn"
exec $WAIT_FOR -- $CMD $SERVER_APP
=======
if [[ -n "$DD_TRACE_HOST" ]]; then
  wait-for-it.sh "$DD_TRACE_HOST" -q -s -t 10 || echo "WARNING: datadog agent unreachable"
fi

exec uvicorn mpcontribs_api.app:app --host 0.0.0.0 --port "$API_PORT"
>>>>>>> ba089932 (Infra changes for rewrite)
