# Logistics Event Processing: Implementation and Setup Notes

## Development environment

- Develop in WSL Ubuntu.
- Keep the project under the WSL filesystem, not `/mnt/c`.
- Use VS Code Remote WSL.
- Use Docker Desktop with WSL integration enabled.
- Use Windows only for GUI tools, browser testing, and presentation editing.

## Disk-space notes

- Ensure sufficient free disk space before pulling Oracle and RabbitMQ images.
- Oracle and RabbitMQ should be run in Docker rather than installed directly into WSL.
- Avoid installing Oracle both directly in WSL and in Docker.

## Docker cleanup before Oracle and RabbitMQ setup

Run before pulling/building Oracle or RabbitMQ images:

```bash
docker system df
docker image prune
docker system df
```

Avoid aggressive cleanup unless old images are definitely no longer needed.

## Compose-first local runtime

- Use `docker-compose.yml` as the source of truth for local Oracle, RabbitMQ, and Python app/test runtime.
- Start local infra with `docker compose up -d oracle rabbitmq`.
- Build app image with `docker compose build app`.
- Run tests in container with `docker compose run --rm app pytest tests/unit` and `docker compose run --rm app pytest tests/integration`.
- Keep manual `docker run` instructions only as fallback/reference notes.

## Oracle setup approach

- Use Oracle in Docker / Docker Compose on the local development PC.
- Oracle is the required database layer for the full application.
- Keep the Python app separate from the Oracle database container.
- Keep Oracle startup scripted and repeatable.
- Keep schema creation scripted.
- Keep PL/SQL package compilation scripted.
- Keep sample-data loading scripted.
- The expected full application path is: start Oracle, apply schema, compile PL/SQL, load sample data, run Python pipeline, run integration tests.

## Oracle runtime strategy

- Primary target: Python app calling working Oracle PL/SQL.
- The full application expects Oracle to be running.
- Integration tests must confirm that Python can connect to Oracle and call the PL/SQL package successfully.
- Unit tests for validation and transformation can run without Oracle.
- Keep synthetic data small enough to inspect manually.
- Keep saved sample output only for quick presentation reference, not as a replacement for the live local runtime.

## RabbitMQ setup approach

- Use RabbitMQ in Docker / Docker Compose on the local development PC.
- RabbitMQ is the message queue layer for the producer/consumer event flow.
- Keep the Python app separate from the RabbitMQ container.
- Use RabbitMQ to demonstrate asynchronous messaging and real-time-style event reception.
- Initial setup starts with Oracle and RabbitMQ Docker containers, then the Python producer/consumer pipeline is built on top.

## Suggested project structure

```text
logistics_event_processing/
  app/
    __init__.py
    main.py
    producer.py
    consumer.py
    rabbitmq_config.py
    validator.py
    transformer.py
    oracle_repository.py
    reporting.py
    logging_config.py

  oracle/
    schema.sql
    package.sql
    seed.sql
    reset.sql

  sample_data/
    incoming_events.jsonl
    invalid_events.jsonl

  tests/
    unit/
      test_validator.py
      test_transformer.py
    integration/
      test_rabbitmq_connection.py
      test_oracle_repository.py
      test_pipeline_end_to_end.py

  reports/
    .gitkeep
    processing_summary.csv

  docs/
    planning/
      logistics_event_processing_implementation_plan.md
      logistics_event_processing_implementation_setup_notes.md
    setup/
      oracle_docker_install_notes.md
      oracle_schema_setup.md
      rabbitmq_docker_install_notes.md

  scripts/
    password_generator.py

  Dockerfile
  docker-compose.yml
  requirements.txt
  README.md
  presentation.md
  set_env_vars.sh
```

## Implementation order

1. Set up Oracle Docker container.
2. Set up RabbitMQ Docker container.
3. Confirm Oracle container starts and can be restarted.
4. Confirm RabbitMQ container starts and the management UI is accessible.
5. Define synthetic GPS event schema.
6. Create sample valid and invalid JSONL event files.
7. Create Oracle schema.
8. Create Oracle seed data.
9. Create Oracle PL/SQL package.
10. Commit and push initial infrastructure/database setup.
11. Write failing happy-path integration tests for the Python-to-Oracle path.
12. Implement Pydantic GPS event validation.
13. Implement transformation logic.
14. Implement Python Oracle repository using `python-oracledb`.
15. Make the Python-to-Oracle happy-path integration tests pass.
16. Add structured logging for accepted and rejected events.
17. Add error handling for invalid payloads and PL/SQL/database errors.
18. Add RabbitMQ producer using `pika`.
19. Add RabbitMQ consumer using `pika`.
19a. Add integration test to test producer -> consumer
20. Connect consumer -> validation -> transformation -> Oracle repository.
21. Add pytest unit tests for validator, transformer, and repository behaviour, covering happy paths and edge cases.
22. Add additional pytest integration tests only where real Oracle behaviour needs to be verified.
23. Add end-to-end happy-path test for sample JSONL -> RabbitMQ -> consumer -> Oracle.
24. Add pandas report that summarises processed GPS records from Oracle.
24a. Log database failures without tracebacks
24b. Change producer into a class
24c. Add integration and unit test for producer.publish_events
24d. Add code for producer.publish_events
24e. Add script to generate time based gps data 
25. Containerise the remaining code, update README run commands.
26. Update `presentation.md` and `README.md`.

## Testing approach

- Unit tests should not require Oracle or RabbitMQ.
- Unit tests should cover both happy paths and edge cases.
- All unit tests should pass before relying on integration test results.
- Integration tests can require Oracle and RabbitMQ.
- Mark Oracle-dependent and RabbitMQ-dependent tests clearly.
- The application is complete when all unit tests pass and the end-to-end integration test passes.

## Presentation notes

- Start `presentation.md` early.
- Keep the presentation aligned with the project.
- Map each implemented feature to a role requirement.
- Do not over-present frontend, AI, MCP, or unrelated projects.
- Focus on data reception, RabbitMQ messaging, validation, transformation, Oracle SQL/PLSQL, logging, archiving, reporting, and testing.

## Local cleanup

After the local development work, remove Oracle and RabbitMQ containers and volumes if no longer needed:

```bash
docker compose down -v
docker image prune
docker volume prune
docker system df
```

If Windows disk space is not returned after cleanup, compact Docker/WSL VHDX files later.