#!/bin/bash

t='*/5 * * * *'
e='notebooks/build'
c=0

[[ -e crontab ]] && rm -v crontab

for host in $API_HOSTS; do
    echo "$t sleep $((c*30+($RANDOM%10)+1)); curl -s $host/$e" >> crontab
    let c++
done

cat crontab
supercronic crontab
