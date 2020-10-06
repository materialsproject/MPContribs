#!/bin/bash

t='*/1 * * * *'
e='notebooks/build'
c=0

for host in $API_HOSTS; do
    echo "$t sleep $((c*5)); curl -s $host/$e" >> crontab
    let c++
done

cat crontab
supercronic crontab
