# Logistics Event Processing System

## 1. Purpose

I built this project as a non-commercial technical demonstration of a small event-processing pipeline.

It demonstrates:

```text
Synthetic GPS events
    -> RabbitMQ
    -> Python consumer
    -> validation / transformation
    -> Oracle PL/SQL
    -> database persistence and reporting
```

The project uses synthetic logistics/GPS events only. It does not use commercial or employer data.

---

## 2. Technical scope

This project demonstrates several backend and data-processing concepts:

- near-real-time operational data processing
- asynchronous message-based processing
- RabbitMQ messaging
- intermediate Python application structure
- ANSI SQL
- Oracle SQL/PLSQL
- Docker/container technology
- automated tests and data validation
- clear documentation and explainable design

It is intentionally compact. The goal is to show a complete, understandable processing path rather than a broad production platform.

---

## 3. System design

The producer and consumer are decoupled through RabbitMQ.

```text
Publisher
    -> RabbitMQ queue
    -> Python consumer
    -> event processor
    -> validator / transformer
    -> Oracle repository
    -> PL/SQL package
    -> Oracle tables
```

The Python code is deliberately separated into clear responsibilities:

- `producer.py` publishes events
- `consumer.py` receives messages and handles ack/reject behaviour
- `event_processor.py` coordinates the processing flow
- `validator.py` checks payload correctness
- `transformer.py` maps valid events into database format
- `oracle_repository.py` calls Oracle PL/SQL
- `reporting.py` produces summary output

---

## 4. Oracle, Docker, and testing

Oracle is used as the persistence layer.

The project includes:

- Oracle schema creation
- PL/SQL package/procedure
- Python-to-Oracle integration using `python-oracledb`
- GPS persistence
- rejected-event handling
- reporting queries

Docker Compose defines the local runtime:

```text
oracle
rabbitmq
app
```

Verified containerised test result:

```text
120 unit tests passed
12 integration tests passed
```

---

## 5. Live proof

The delayed synthetic publisher simulates GPS events arriving over time.

Demo commands:

```bash
docker compose run --rm app pytest tests/unit
docker compose run --rm app pytest tests/integration
docker compose run --rm app python -m app.main
docker compose run --rm app python scripts/publish_synthetic_gps_events.py
```

Open an Oracle SQL prompt:

```bash
docker exec -i logistics-oracle sqlplus "$LOGISTICS_DB_USER"/"$LOGISTICS_DB_PASSWORD"@FREEPDB1 <<EOF
SELECT COUNT(*) FROM gps;
EXIT;
EOF
```

Observed during testing:

```text
112 -> 116 -> 118 -> 126
```

This confirms the full path:

```text
published -> queued -> consumed -> validated/transformed -> persisted
```

Additional pasteable query for the latest 10 producer hashes (newest shown last):

```bash
docker exec -i logistics-oracle sqlplus "$LOGISTICS_DB_USER"/"$LOGISTICS_DB_PASSWORD"@FREEPDB1 <<EOF
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

---

## 6. Trade-offs and next steps

Intentional trade-offs:

- synchronous Python consumer for simplicity
- RabbitMQ provides the asynchronous processing boundary
- explicit Oracle initialization rather than hidden startup behaviour
- focused proof-of-work project rather than a broad production platform

Natural next steps:

- automate Oracle schema initialization
- add a lightweight CI workflow for unit tests
- add readiness checks
- add retry/dead-letter behaviour if required
- expand monitoring and reporting

Closing point:

This project is intentionally small, but it demonstrates clear data flow, simple maintainable design, data correctness, repeatable runtime setup, and tests around both happy paths and failure paths.