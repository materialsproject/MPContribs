#!/bin/bash

set -e
PMGRC=$HOME/.pmgrc.yaml
[[ ! -e $PMGRC ]] && echo "PMG_DUMMY_VAR: dummy" >"$PMGRC"

CMD="jupyter kernelgateway"

if [[ -n "$DD_TRACE_HOST" ]]; then
  wait-for-it.sh "$DD_TRACE_HOST" -q -s -t 10 && CMD="ddtrace-run $CMD" || echo "WARNING: datadog agent unreachable"
fi

# Logging (structured JSON, incl. the request log) is configured in
# jupyter_kernel_gateway_config.py (JUPYTER_CONFIG_DIR)
exec $CMD
