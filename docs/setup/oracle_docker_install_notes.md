# Oracle Docker Install Notes

## Preferred path now: Docker Compose

Use Docker Compose as the primary way to start Oracle and RabbitMQ for this project.

From the project root:

```bash
docker compose up -d oracle rabbitmq
```

The Compose definitions are now the source of truth for container creation/startup.

This file keeps the previous manual `docker run` commands as reference/troubleshooting notes.

## Purpose

Install and run Oracle Database Free locally in Docker for the logistics event processing application. The Python application will use Oracle as the database layer and call Oracle PL/SQL through `python-oracledb`.

## Prerequisites

- WSL Ubuntu development environment.
- Docker Desktop installed on Windows.
- Docker Desktop WSL integration enabled.
- Run Docker commands from WSL.
- At least 25-30 GB free disk space recommended.

## Image

Use Oracle Database Free from Oracle Container Registry.

```bash
docker pull container-registry.oracle.com/database/free:latest
```
Oracle's current get-started page lists this pull command for Oracle Database Free container images.

Set secrets in ~/.oracle/.env
```bash
mkdir -p ~/.oracle
code -r ~/.oracle/.env
```

Set the following passwords/secrets:
```bash
ORACLE_ADMIN_PASSWORD=<admin password>
LOGISTICS_DB_USER=logistics
LOGISTICS_DB_PASSWORD=<app user password>
ORACLE_DSN=localhost:1521/FREEPDB1
```

Set permissions for the directory and file:
```bash
chmod 700 ~/.oracle
chmod 600 ~/.oracle/.env
```
Load these variables in your shell before running Docker commands:

```bash
set -a
source ~/.oracle/.env
set +a
```

## Start Oracle container
Make sure you are in the same terminal where you sourced the environment variables

```bash
docker run -d \
  --name logistics-oracle \
  -p 1521:1521 \
  -e ORACLE_PWD="$ORACLE_ADMIN_PASSWORD" \
  container-registry.oracle.com/database/free:latest
```

Manual reference only. Preferred startup is via `docker compose up -d oracle rabbitmq`.

## Check container status

```bash
docker ps
```

Follow startup logs:

```bash
docker logs -f logistics-oracle
```

Wait until the database has finished starting before applying schema scripts or running Python integration tests.

## Expected connection details

```text
Host: localhost
Port: 1521
Service: FREEPDB1
SYS/SYSTEM password: value of ORACLE_ADMIN_PASSWORD
Application user: value of LOGISTICS_DB_USER
Application password: value of LOGISTICS_DB_PASSWORD
Python DSN: value of ORACLE_DSN
```

## Test SQL*Plus connection from inside the container

```bash
docker exec -it logistics-oracle sqlplus system/"$ORACLE_ADMIN_PASSWORD"@FREEPDB1
```

Exit SQL*Plus:

```sql
exit
```

## Create application user

Connect as SYSTEM and create the application schema/user from the shell variables:

```bash
docker exec -i logistics-oracle sqlplus system/"$ORACLE_ADMIN_PASSWORD"@FREEPDB1 <<SQL
CREATE USER $LOGISTICS_DB_USER IDENTIFIED BY "$LOGISTICS_DB_PASSWORD";
GRANT CONNECT, RESOURCE TO $LOGISTICS_DB_USER;
ALTER USER $LOGISTICS_DB_USER QUOTA UNLIMITED ON USERS;
EXIT;
SQL
```

## Stop and restart Oracle container

The Oracle container may stop if Windows shuts down, Docker Desktop stops, WSL shuts down, or the container is stopped manually.

Restart the existing Oracle container:

```bash
docker start logistics-oracle
```

Compose equivalent:

```bash
docker compose start oracle
```

Follow startup logs:

```bash
docker logs -f logistics-oracle
```

Wait until Oracle has finished starting before connecting, applying SQL scripts, or running integration tests.

Note: The Oracle admin password and application user details do not need to be passed to the container again when using `docker start`. They were applied when the database was first created.

### Important distinction

```text
docker stop logistics-oracle
docker start logistics-oracle
```

keeps the existing database state, including users, passwords, tables, PL/SQL packages, and data.

```text
docker rm -f logistics-oracle
docker run ...
```

removes and recreates the container. Without a persistent Docker volume, that starts a fresh database and requires the setup steps again.


## Python dependency

Install `python-oracledb` in the project virtual environment:

```bash
pip install python-oracledb
```

Or include it in `requirements.txt`:

```text
python-oracledb
```

## Docker Compose note

Compose is now implemented and is the recommended startup workflow.

Use this file's manual commands as fallback/reference only.

## Runtime expectation

The application expects Oracle to be running. Integration tests should confirm that Python can connect to Oracle and call the PL/SQL package successfully.
