#!/bin/bash

set -e
zzz=$(($DEPLOYMENT * 60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

pmgrc=$HOME/.pmgrc.yaml
[[ ! -e $pmgrc ]] && echo "PMG_DUMMY_VAR: dummy" >$pmgrc

CMD="gunicorn \"mpcontribs.api:create_app()\""

if [[ -n "$DD_TRACE_HOST" ]]; then
	wait-for-it.sh $DD_TRACE_HOST -q -s -t 10 && CMD="ddtrace-run $CMD"
fi

exec wait-for-it.sh $JUPYTER_GATEWAY_HOST -q -t 50 -- $CMD
