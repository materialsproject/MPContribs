#!/bin/bash

gunicorn -b 0.0.0.0:$PORTAL_PORT -k gevent -w $NWORKERS --access-logfile - --error-logfile - --log-level debug $RELOAD wsgi
