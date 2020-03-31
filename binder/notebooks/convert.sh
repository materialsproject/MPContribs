#!/bin/bash

out=/app/mpcontribs/portal/templates/notebooks/
[[ -d $out ]] && rm -rv $out && mkdir -pv $out

for d in `ls -1d /app/notebooks/*/`; do
    name=`basename $d`
    for i in `ls -1 $d*.ipynb`; do
        echo $i
        /venv/bin/jupyter nbconvert --to html --template basic --output-dir=$out$name $i
    done
done
