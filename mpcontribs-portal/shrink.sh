#!/bin/bash

while IFS= read -r jpg
do
    convert "$jpg""[150>]" "$jpg"
done < "$1"
