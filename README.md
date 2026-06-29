# logistics_event_processing

Local logistics event processing PoC using:

- Oracle Database Free
- RabbitMQ (`rabbitmq:3-management`)
- Python (`pytest`, `pika`, `oracledb`, `pydantic`)

## Preferred local infrastructure workflow (Docker Compose)

Use Docker Compose to define and start local Oracle and RabbitMQ.

If you previously created manual containers with the same names, remove them once before first Compose use:

```bash
docker stop logistics-oracle logistics-rabbitmq 2>/dev/null || true
docker rm logistics-oracle logistics-rabbitmq 2>/dev/null || true
```

```bash
docker compose up -d oracle rabbitmq
```

Build the Python app/test image:

```bash
docker compose build app
```

Run tests inside the app container:

```bash
docker compose run --rm app pytest tests/unit
docker compose run --rm app pytest tests/integration
```

Stop everything:

```bash
docker compose down
```

To also remove persistent Oracle/RabbitMQ data:

```bash
docker compose down -v
```

## Environment variables and local vs Compose networking

For non-container local runs, this project still uses:

```bash
source set_env_vars.sh
```

`set_env_vars.sh` is for shell-based local development. Docker Compose reads exported shell variables or a `.env` file; it does not directly parse `set_env_vars.sh`.

Before running Docker Compose, either:

1. source the script in the same shell so variables are exported, then run Compose, or
2. create a Compose-compatible `.env` file in the project root (or use `--env-file`).

Example:

```bash
source set_env_vars.sh
docker compose up -d oracle rabbitmq
```

`set_env_vars.sh` loads secrets from:

- `~/.oracle/.env`
- `~/.rabbitmq/.env`

Those files should provide:

- `RABBITMQ_USER`
- `RABBITMQ_PASSWORD`
- `RABBITMQ_HOST`
- `RABBITMQ_PORT`
- `RABBITMQ_MANAGEMENT_PORT`
- `RABBITMQ_QUEUE`
- `ORACLE_ADMIN_PASSWORD`
- `LOGISTICS_DB_USER`
- `LOGISTICS_DB_PASSWORD`
- `ORACLE_DSN`

Important hostname difference:

- Local non-container runs commonly use `localhost` values.
- Compose container-to-container traffic must use service names.
  - RabbitMQ host is `rabbitmq` inside the `app` container.
  - Oracle DSN host is `oracle` inside the `app` container (`oracle:1521/FREEPDB1`).

`docker-compose.yml` sets these app container values explicitly so tests run with Compose networking.

## Oracle first-time initialization after container start

Compose starts the Oracle container but does not auto-apply schema/package/seed yet.

After `docker compose up -d oracle rabbitmq`, wait for Oracle startup logs:

```bash
docker logs -f logistics-oracle
```

Then create application user (if needed):

```bash
source set_env_vars.sh

docker exec -i logistics-oracle sqlplus system/"$ORACLE_ADMIN_PASSWORD"@FREEPDB1 <<SQL
CREATE USER $LOGISTICS_DB_USER IDENTIFIED BY "$LOGISTICS_DB_PASSWORD";
GRANT CONNECT, RESOURCE TO $LOGISTICS_DB_USER;
ALTER USER $LOGISTICS_DB_USER QUOTA UNLIMITED ON USERS;
EXIT;
SQL
```

This user-creation block is only for a fresh Oracle volume. If the user/schema already exists, skip user creation and reapply only the SQL scripts you need.

If you reset with `docker compose down -v`, Oracle data is removed and this first-time initialization is required again.

Apply SQL scripts:

```bash
docker exec -i logistics-oracle sqlplus "$LOGISTICS_DB_USER"/"$LOGISTICS_DB_PASSWORD"@FREEPDB1 < oracle/schema.sql
docker exec -i logistics-oracle sqlplus "$LOGISTICS_DB_USER"/"$LOGISTICS_DB_PASSWORD"@FREEPDB1 < oracle/package.sql
docker exec -i logistics-oracle sqlplus "$LOGISTICS_DB_USER"/"$LOGISTICS_DB_PASSWORD"@FREEPDB1 < oracle/seed.sql
```

This keeps startup reliable and explicit for interview/demo use.
