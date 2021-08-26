#!/bin/bash

supervisorctl start api
# TODO only start worker/scheduler on first AWS task/container?

if [ ! -z ${ECS_CONTAINER_METADATA_URI_V4} ]; then
    http ${ECS_CONTAINER_METADATA_URI_V4}
fi

supervisorctl start worker
supervisorctl start scheduler
