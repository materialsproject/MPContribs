#!/bin/bash

supervisorctl start api
supervisorctl start worker
supervisorctl start scheduler
