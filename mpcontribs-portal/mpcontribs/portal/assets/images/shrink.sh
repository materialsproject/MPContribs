#!/bin/bash

while IFS= read -r jpg
do
    convert "$jpg""[300>]" "$jpg"
done < "$1"
