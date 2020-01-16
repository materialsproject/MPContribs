#!/bin/sh
set -e

if [ ! -e /app/mpcontribs/api/contributions/formulae.json ]; then
    python mpcontribs/api/contributions/generate_formulae.py
fi

exec "$@"
