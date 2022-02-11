#!/bin/bash

zzz=$(($DEPLOYMENT*60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

pmgrc=$HOME/.pmgrc.yaml
[[ ! -e $pmgrc ]] && echo "PMG_DUMMY_VAR: dummy" > $pmgrc
python manage.py migrate --noinput
exec wait-for-it.sh $MPCONTRIBS_API_HOST -q -s -t 60 -- ddtrace-run gunicorn wsgi
