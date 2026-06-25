````md
# Logistics Event Processing System

## 1. Purpose of the project

This is a small purpose-built logistics event processing application.

The aim is to show a clear vertical slice of a production-style data reception, messaging, validation, transformation, persistence, and reporting system.

The application uses synthetic logistics events only. It does not use commercial or employer data.

---

## 2. Why this project is relevant

The role involves data reception, transformation, validation, logging, monitoring, archiving, and accurate data processing.

This project is designed to show those same patterns in a compact local project:

- asynchronous event reception
- RabbitMQ message queue
- Python producer and consumer
- Python validation and transformation
- Oracle SQL/PLSQL persistence
- rejected-event handling
- archiving
- logging
- reporting
- automated tests

---

## 3. Current progress

The first stage has been infrastructure setup.

Completed so far:

- Oracle Database Free container setup
- Oracle credential handling through `~/.oracle/.env`
- Oracle container start/restart process documented
- RabbitMQ container setup
- RabbitMQ credential handling through `~/.rabbitmq/.env`
- RabbitMQ management UI access confirmed
- Docker-based local development flow established

The Python application code is still to be built on top of this infrastructure.

---

## 4. Current local architecture

The current architecture is planned around separate infrastructure containers and a Python application layer.

```text
Oracle container      -> database and PL/SQL layer
RabbitMQ container    -> message queue layer
Python app in WSL     -> producer, consumer, validation, transformation, reporting
```

The intended end-to-end flow is:

```text
Synthetic logistics event producer
        ↓
RabbitMQ queue
        ↓
Python consumer
        ↓
Pydantic validation
        ↓
Python transformation
        ↓
Oracle PL/SQL package
        ↓
Processed / rejected / archived records
        ↓
Pandas summary report
```

---

## 5. Oracle setup

Oracle is used as the database and PL/SQL layer.

The planned role of Oracle is to:

- store validated logistics events
- store rejected events with error reasons
- maintain archive tables
- expose PL/SQL procedures/packages for event processing
- provide a realistic SQL/PLSQL integration point for Python

The Python application will connect to Oracle using `python-oracledb`.

Current Oracle status:

- Oracle container has been set up locally
- credentials are stored outside the project directory
- restart behaviour has been documented
- schema scripts and PL/SQL package are still to be created

---

## 6. RabbitMQ setup

RabbitMQ is used as the message queue layer.

The planned role of RabbitMQ is to:

- receive synthetic logistics events from a Python producer
- queue events for asynchronous processing
- allow a Python consumer to read and process events
- demonstrate a real messaging-framework pattern

The Python application will connect to RabbitMQ using `pika`.

Current RabbitMQ status:

- RabbitMQ container has been set up locally
- management UI is available on port `15672`
- AMQP application port is available on `5672`
- credentials are stored outside the project directory
- queue creation is still to be implemented in Python

---

## 7. Environment and secret handling

Local secrets are stored outside the project directory.

Oracle settings are stored in:

```text
~/.oracle/.env
```

RabbitMQ settings are stored in:

```text
~/.rabbitmq/.env
```

This avoids committing local credentials to the repository.

The `.env` files are loaded into each WSL terminal session before running commands that depend on those variables.

---

## 8. Next implementation steps

Next steps are:

1. Define the synthetic logistics event schema.
2. Create valid and invalid sample event files.
3. Add RabbitMQ producer and consumer code.
4. Add Pydantic validation.
5. Add transformation logic.
6. Create Oracle schema tables.
7. Create Oracle PL/SQL package.
8. Connect the Python consumer to Oracle.
9. Add rejected-event handling.
10. Add logging, archive handling, reporting, and tests.

---

## 9. Intended end-to-end behaviour

The intended end-to-end behaviour is:

1. A synthetic logistics event is published to RabbitMQ.
2. The Python consumer receives the event.
3. The event is validated.
4. Valid events are transformed into a normalised processing format.
5. Invalid events are rejected with an error reason.
6. Valid events are passed into Oracle PL/SQL.
7. Oracle stores processed, rejected, and archived records.
8. A pandas report summarises processing outcomes.

---

## 10. What this demonstrates

This project is intended to demonstrate:

- Python backend development
- real-time-style data processing
- asynchronous messaging
- Docker-based local infrastructure
- SQL and PL/SQL integration
- validation and error handling
- testable processing logic
- practical system decomposition

The project is deliberately small, but the architecture mirrors the shape of larger production data-processing systems.
````
