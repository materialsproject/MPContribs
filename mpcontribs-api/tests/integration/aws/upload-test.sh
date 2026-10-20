#!/bin/bash

curl -T $0 $1 -w "%{http_code}\n" -o /dev/null -s

