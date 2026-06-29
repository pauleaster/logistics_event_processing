# RabbitMQ Docker Install Notes

## Preferred path now: Docker Compose

Use Docker Compose as the primary way to start RabbitMQ and Oracle for this project.

From the project root:

```bash
docker compose up -d oracle rabbitmq
```

The Compose definitions are now the source of truth for container creation/startup.

This file keeps the previous manual `docker run` commands as reference/troubleshooting notes.

## Purpose

Install and run RabbitMQ locally in Docker for the logistics event processing application. RabbitMQ will provide the message queue layer between the synthetic event producer and the Python consumer.

The Python application will publish logistics events to RabbitMQ and consume them using `pika`.

## Prerequisites

- WSL Ubuntu development environment.
- Docker Desktop installed on Windows.
- Docker Desktop WSL integration enabled.
- Run Docker commands from WSL.
- Oracle container setup completed or in progress.
- Python virtual environment available for the logistics event processing project.

## Image

Use the RabbitMQ management image so that the browser-based management UI is available.

```bash
docker pull rabbitmq:3-management
```

## Secrets file

Store local RabbitMQ settings outside the project directory.

```bash
mkdir -p ~/.rabbitmq
code -r ~/.rabbitmq/.env
```

Set the following values in `~/.rabbitmq/.env`:

```bash
RABBITMQ_USER=logistics
RABBITMQ_PASSWORD=<rabbitmq password>
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_MANAGEMENT_PORT=15672
RABBITMQ_QUEUE=logistics_events
```

Use a long alphanumeric password to avoid shell and connection-string quoting issues.

Set permissions for the directory and file:

```bash
chmod 700 ~/.rabbitmq
chmod 600 ~/.rabbitmq/.env
```

Export the settings into the current shell environment:

```bash
set -a
source ~/.rabbitmq/.env
set +a
```

## Start RabbitMQ container
Make sure you are in the same terminal where you sourced the environment variables

```bash
docker run -d \
  --name logistics-rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER="$RABBITMQ_USER" \
  -e RABBITMQ_DEFAULT_PASS="$RABBITMQ_PASSWORD" \
  rabbitmq:3-management
```

Manual reference only. Preferred startup is via `docker compose up -d oracle rabbitmq`.

## Check container status

```bash
docker ps
```

Follow startup logs:

```bash
docker logs -f logistics-rabbitmq
```

Wait until RabbitMQ has finished starting before running the Python producer or consumer.

## Expected connection details

```text
Host: localhost
AMQP port: 5672
Management UI port: 15672
Management UI URL: http://localhost:15672
```

## Open RabbitMQ management UI

Open this in a browser:

```text
http://localhost:15672
```

Log in with:

```text
Username: value of RABBITMQ_USER
Password: value of RABBITMQ_PASSWORD
```

## Stop and restart RabbitMQ container

RabbitMQ may stop if Windows shuts down, Docker Desktop stops, WSL shuts down, or the container is stopped manually.

Check whether the container is currently running:

```bash
docker ps
```

Show running and stopped containers:

```bash
docker ps -a
```

Restart the existing RabbitMQ container:

```bash
docker start logistics-rabbitmq
```

Compose equivalent:

```bash
docker compose start rabbitmq
```

Follow startup logs:

```bash
docker logs -f logistics-rabbitmq
```

The RabbitMQ username, password, and queue state do not need to be passed to the container again when using `docker start`. They were applied when the container was first created.

The `~/.rabbitmq/.env` file is still useful for shell commands and Python application settings. Load it again in any new WSL terminal before running commands that use the variables:

```bash
set -a
source ~/.rabbitmq/.env
set +a
```

Important distinction:

```text
docker stop logistics-rabbitmq
docker start logistics-rabbitmq
```

keeps the existing container state.

```text
docker rm -f logistics-rabbitmq
docker run ...
```

removes and recreates the container. The RabbitMQ user/password will be reapplied from the environment variables when the container is recreated.

## Python dependency

Install `pika` in the project virtual environment:

```bash
pip install pika
```

Or include it in `requirements.txt`:

```text
pika
```

## Python environment variables

The Python app should use the values already loaded from:

```bash
set -a
source ~/.rabbitmq/.env
set +a
```

Expected variables:

```bash
RABBITMQ_USER
RABBITMQ_PASSWORD
RABBITMQ_HOST
RABBITMQ_PORT
RABBITMQ_QUEUE
```

## Minimal Python connection check

Create a quick temporary check once the project environment is ready:

```bash
python - <<'PY'
import os
import pika

credentials = pika.PlainCredentials(
    os.environ["RABBITMQ_USER"],
    os.environ["RABBITMQ_PASSWORD"],
)

params = pika.ConnectionParameters(
    host=os.environ.get("RABBITMQ_HOST", "localhost"),
    port=int(os.environ.get("RABBITMQ_PORT", "5672")),
    credentials=credentials,
)

connection = pika.BlockingConnection(params)
channel = connection.channel()

queue_name = os.environ.get("RABBITMQ_QUEUE", "logistics_events")
channel.queue_declare(queue=queue_name, durable=True)

print(f"Connected to RabbitMQ and declared queue: {queue_name}")

connection.close()
PY
```

## Remove RabbitMQ container

This removes the container.

```bash
docker rm -f logistics-rabbitmq
```

## Docker Compose note

Compose is now implemented and is the recommended startup workflow.

Use this file's manual commands as fallback/reference only.

## Runtime expectation

The application expects RabbitMQ and Oracle to be running.

The expected flow is:

```text
Python producer
  -> RabbitMQ queue
  -> Python consumer
  -> validation/transformation
  -> Oracle PL/SQL
  -> processed/rejected/archive tables
```

Integration tests should confirm that Python can connect to RabbitMQ, declare the queue, publish a test event, consume it, and pass it into the processing pipeline.