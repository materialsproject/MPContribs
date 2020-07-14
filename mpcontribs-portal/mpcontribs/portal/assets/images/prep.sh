#!/bin/bash

[[ $# -ne 1 ]] && echo "USAGE: ./prep.sh <image>" && exit

img=$1
name=${img%%.*}
ext=${img##*.}

convert -border 2 -bordercolor white \
    $img \
    -background white -alpha remove -alpha off \
    -resize 500 \
    $name-convert.png

pngquant $name-convert.png
rm -v $name-convert.png
mv -v $name-convert-fs8.png $name.png
