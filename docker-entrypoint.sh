#!/bin/sh
set -e

/venv/bin/python manage.py migrate --noinput

# TODO replace load_client cell for api_key
out=mpcontribs-portal/mpcontribs/portal/templates
#/venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/contribute/get_started.ipynb && \
for i in `ls -1 notebooks/*/*.ipynb`; do
   /venv/bin/jupyter nbconvert --to html --template basic --output-dir=$out/`dirname $i` $i
done

exec "$@"
