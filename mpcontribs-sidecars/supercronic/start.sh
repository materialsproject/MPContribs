#!/bin/bash

t='*/1 * * * *'
e='notebooks/build'

for host in $API_HOSTS; do
    echo "$t curl -s $host/$e" >> crontab
    echo "$t sleep 5; curl -s $host/$e" >> crontab
    echo "$t sleep 10; curl -s $host/$e" >> crontab
done

cat crontab
supercronic crontab
