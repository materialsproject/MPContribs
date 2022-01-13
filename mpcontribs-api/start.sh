#!/bin/bash

DD_GEVENT_PATCH_ALL=true gunicorn -c gunicorn.conf.py \
    -b 0.0.0.0:$API_PORT -k gevent -w $NWORKERS \
    --access-logfile - --error-logfile - --log-level debug $RELOAD \
    --max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER \
    "mpcontribs.api:create_app()"
