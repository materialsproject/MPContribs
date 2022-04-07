#!/bin/bash

zzz=$(($DEPLOYMENT*60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

if [ ! -z "$METADATA_URI" ]; then
    task_ip=`curl ${METADATA_URI}/task | jq -r '.Containers[0].Networks[0].IPv4Addresses[0]'`
    export MPCONTRIBS_CLIENT_HOST=$task_ip:$MPCONTRIBS_API_PORT
else
    export MPCONTRIBS_CLIENT_HOST=$MPCONTRIBS_API_HOST
fi

pmgrc=$HOME/.pmgrc.yaml
[[ ! -e $pmgrc ]] && echo "PMG_DUMMY_VAR: dummy" > $pmgrc
python manage.py migrate --noinput
exec wait-for-it.sh $MPCONTRIBS_API_HOST -q -s -t 60 -- ddtrace-run gunicorn wsgi
