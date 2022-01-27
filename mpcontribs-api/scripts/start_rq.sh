#!/bin/bash

zzz=$(($DEPLOYMENT*60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

exec wait-for-it.sh $JUPYTER_GATEWAY_HOST -s -t 50 -- wait-for-it.sh $MPCONTRIBS_API_HOST -s -t 15 -- ddtrace-run flask rq $1
