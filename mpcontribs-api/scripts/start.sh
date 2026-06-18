#!/bin/bash

set -e
zzz=$((DEPLOYMENT * 60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

PMGRC=$HOME/.pmgrc.yaml
[[ ! -e "$PMGRC" ]] && echo "PMG_DUMMY_VAR: dummy" >"$PMGRC"

set -x

# No wait for the OTLP collector: the OTEL batch processors tolerate an unavailable endpoint
# (they retry and drop), so startup must not block on it.
exec uvicorn mpcontribs_api.app:app --host 0.0.0.0 --port "$API_PORT"
