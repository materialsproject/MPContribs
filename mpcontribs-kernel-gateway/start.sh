#!/bin/bash

set -e
pmgrc=$HOME/.pmgrc.yaml
[[ ! -e $pmgrc ]] && echo "PMG_DUMMY_VAR: dummy" >$pmgrc

CMD="jupyter kernelgateway"

if [[ -n "$DD_TRACE_HOST" ]]; then
	wait-for-it.sh $DD_TRACE_HOST -q -s -t 10 && CMD="ddtrace-run $CMD"
fi

echo $CMD
exec $CMD --KernelGatewayApp.log_format='%(asctime)s,%(msecs)03d %(levelname)s [%(name)s] [%(module)s:%(lineno)d] - %(message)s'
