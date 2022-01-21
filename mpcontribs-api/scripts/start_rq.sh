#!/bin/bash

set -a
source $ENV_FILE
env

wait-for-it.sh $JUPYTER_GATEWAY_HOST -s -t 50 -- wait-for-it.sh $MPCONTRIBS_API_HOST -s -t 15 -- ddtrace-run flask rq $1
