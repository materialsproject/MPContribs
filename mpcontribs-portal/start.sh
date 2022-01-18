#!/bin/bash

gunicorn -c gunicorn.conf.py \
    -b 0.0.0.0:$PORTAL_PORT -k gevent -w $NWORKERS \
    --access-logfile - --error-logfile - --log-level debug $RELOAD \
    --max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER \
    wsgi
