#!/bin/bash

gunicorn -b 0.0.0.0:$API_PORT -k gevent -w $NWORKERS \
    --access-logfile - --error-logfile - --log-level debug $RELOAD \
    --max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER \
    "mpcontribs.api:create_app()"
