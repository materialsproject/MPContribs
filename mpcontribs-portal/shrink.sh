#!/bin/bash

while IFS= read -r jpg
do
    convert "$jpg""[275>]" "$jpg"
done < "$1"
