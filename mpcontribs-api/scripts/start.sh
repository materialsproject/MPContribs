#!/bin/bash

zzz=$(($DEPLOYMENT*60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

pmgrc=$HOME/.pmgrc.yaml
[[ ! -e $pmgrc ]] && echo "PMG_DUMMY_VAR: dummy" > $pmgrc

exec wait-for-it.sh $JUPYTER_GATEWAY_HOST -q -t 50 -- ddtrace-run gunicorn "mpcontribs.api:create_app()"
