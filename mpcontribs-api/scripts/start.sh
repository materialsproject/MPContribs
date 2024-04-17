#!/bin/bash

set -e
zzz=$(($DEPLOYMENT * 60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

pmgrc=$HOME/.pmgrc.yaml
[[ ! -e $pmgrc ]] && echo "PMG_DUMMY_VAR: dummy" >$pmgrc

STATS_ARG=""
SERVER_APP="mpcontribs.api:create_app()"
WAIT_FOR="wait-for-it.sh $JUPYTER_GATEWAY_HOST -q -t 50"

if [[ -n "$DD_TRACE_HOST" ]]; then
	wait-for-it.sh $DD_TRACE_HOST -q -s -t 10 && STATS_ARG="--statsd-host $DD_AGENT_HOST:8125"
fi

if [[ -n "$STATS_ARG" ]]; then
	exec $WAIT_FOR -- ddtrace-run gunicorn $STATS_ARG $SERVER_APP
else
	exec $WAIT_FOR -- gunicorn $SERVER_APP
fi
