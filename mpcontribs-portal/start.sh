#!/bin/bash

zzz=$(($DEPLOYMENT*60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

python manage.py migrate --noinput
exec wait-for-it.sh $MPCONTRIBS_API_HOST -q -s -t 60 -- ddtrace-run gunicorn wsgi
