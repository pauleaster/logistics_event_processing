# Logistics Event Processing Implementation Plan

## Brief description

Build a small purpose-specific logistics event processing application.

The application simulates a logistics GPS telemetry stream, receives synthetic driver and vehicle location events through RabbitMQ, validates each event, transforms valid records into a normalised processing format, stores and processes the data through Oracle SQL/PLSQL, logs rejected events, produces a pandas summary report, and includes pytest unit and integration tests.

The application provides a clear vertical slice of a production-style data reception, validation, transformation, storage, and reporting system.

## Application purpose

The application processes synthetic logistics events such as dispatch, pickup, delivery scan, failed delivery, and return-to-depot events.

Each incoming event is received from a RabbitMQ queue and checked for required fields, valid event type, timestamp, driver identifier, delivery identifier, postcode, and status. Valid events are transformed and stored for downstream use. Invalid events are rejected into an error table with an explanation.

## Scope checklist

1. Synthetic logistics event stream
2. RabbitMQ message queue
3. Python producer / receiver
4. Pydantic validation
5. Python transformation logic
6. Oracle tables
7. Oracle PL/SQL package
8. Python calls PL/SQL using `python-oracledb`
9. Error table for rejected records
10. Archive table for processed records
11. Logging
12. Pandas summary report
13. Pytest unit tests
14. Pytest integration tests
15. Oracle and RabbitMQ Docker containers / Docker Compose if stable
16. README with run commands
17. 10-minute presentation mapping each part to relevant role requirements

## Build note

The 10-minute presentation can start as a Markdown file developed in parallel with the code. The initial setup starts with Oracle and RabbitMQ Docker containers, then the Python producer/consumer pipeline is built on top. Starting with integration tests is a reasonable approach: define the expected end-to-end behaviour first, then build the application until those tests pass.