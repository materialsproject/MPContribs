#!/bin/bash

exec wait-for-it.sh $JUPYTER_GATEWAY_HOST -s -t 50 -- wait-for-it.sh $MPCONTRIBS_API_HOST -s -t 15 -- ddtrace-run flask rq $1
