#!/bin/bash

gunicorn -b 0.0.0.0:$API_PORT -k gevent -w $NWORKERS --access-logfile - --error-logfile - --log-level debug $RELOAD "mpcontribs.api:create_app()"
