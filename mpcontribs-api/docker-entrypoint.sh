#!/bin/sh
set -e

python supervisord/conf.py

exec "$@"
