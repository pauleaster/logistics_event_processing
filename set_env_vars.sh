#!/bin/bash
# This script is used to set environment variables for Oracle and RabbitMQ from their respective .env files.

set -a
source ~/.oracle/.env
source ~/.rabbitmq/.env
set +a
