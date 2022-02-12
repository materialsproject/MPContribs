#!/bin/bash

pmgrc=$HOME/.pmgrc.yaml
[[ ! -e $pmgrc ]] && echo "PMG_DUMMY_VAR: dummy" > $pmgrc

exec wait-for-it.sh $DD_TRACE_HOST -s -q -t 60 -- ddtrace-run jupyter kernelgateway \
    --KernelGatewayApp.log_format='%(asctime)s,%(msecs)03d %(levelname)s [%(name)s] [%(module)s:%(lineno)d] - %(message)s'


