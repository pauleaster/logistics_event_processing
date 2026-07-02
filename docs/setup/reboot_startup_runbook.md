# Reboot Startup Runbook

Minimal commands to bring the local logistics stack back up after a laptop restart or battery loss.

Use separate terminals and source the environment in each one before running any Docker command.

## Terminal 1: start Oracle and RabbitMQ

```bash
cd ~/repos/logistics/logistics_event_processing
source set_env_vars.sh
docker compose up -d oracle rabbitmq
docker logs -f logistics-oracle
```

Press Ctrl+C once Oracle is ready.

If the containers already exist and only need restarting:

```bash
source set_env_vars.sh
docker compose start oracle rabbitmq
```

## Terminal 1 (reuse): build, run tests, then start the app consumer

```bash
cd ~/repos/logistics/logistics_event_processing
source set_env_vars.sh
docker compose build app
docker compose run --rm app pytest tests/unit
docker compose run --rm app pytest tests/integration
docker compose run --rm app python -m app.main
```

## Terminal 2: publish synthetic GPS events

```bash
cd ~/repos/logistics/logistics_event_processing
source set_env_vars.sh
docker compose run --rm app python scripts/publish_synthetic_gps_events.py
```

## Terminal 3: correlate producer IDs and app log hashes from Oracle

`gps.external_event_id` is the hash shown as `Published event: ...`.

Use this query to show the latest 10 hashes in order, with the newest at the bottom:

```bash
cd ~/repos/logistics/logistics_event_processing
source set_env_vars.sh
docker exec -i logistics-oracle sqlplus "$LOGISTICS_DB_USER/$LOGISTICS_DB_PASSWORD@FREEPDB1" <<EOF
SET LINESIZE 220
SET PAGESIZE 50
COLUMN producer_event_id FORMAT A16
SELECT producer_event_id
FROM (
  SELECT external_event_id AS producer_event_id,
         created_at
  FROM gps
  ORDER BY created_at DESC
  FETCH FIRST 10 ROWS ONLY
) recent
ORDER BY created_at ASC;
EXIT;
EOF
```