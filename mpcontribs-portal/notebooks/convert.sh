#!/bin/bash

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 INDIR OUTDIR"
  exit 1
fi

indir=$1
[[ ! -d $indir ]] && echo "$indir does not exist!" && exit 1
outdir=$2
[[ -d $outdir ]] && rm -rv $outdir && mkdir -pv $outdir

for d in `ls -1d $indir/*/`; do
    name=`basename $d`
    jupyter nbconvert --to html --template basic --output-dir=$outdir$name $i `ls $d*.ipynb`
done
