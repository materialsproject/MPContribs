#!/bin/bash

set -e
zzz=$((DEPLOYMENT * 60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

if [ -n "$METADATA_URI" ]; then
  task_ip=$(curl "${METADATA_URI}/task" | jq -r '.Containers[0].Networks[0].IPv4Addresses[0]')
  export MPCONTRIBS_CLIENT_HOST=$task_ip:$MPCONTRIBS_API_PORT
else
  export MPCONTRIBS_CLIENT_HOST=$MPCONTRIBS_API_HOST
fi

PMGRC=$HOME/.pmgrc.yaml
[[ ! -e "$PMGRC" ]] && echo "PMG_DUMMY_VAR: dummy" >"$PMGRC"
python manage.py migrate --noinput

CMD="gunicorn wsgi"

if [[ -n "$DD_TRACE_HOST" ]]; then
  wait-for-it.sh "$DD_TRACE_HOST" -q -s -t 10 && CMD="ddtrace-run $CMD" || echo "WARNING: datadog agent unreachable"
fi

exec wait-for-it.sh "$MPCONTRIBS_API_HOST" -q -s -t 60 -- $CMD
