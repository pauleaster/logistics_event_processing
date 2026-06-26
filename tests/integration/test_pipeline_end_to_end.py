"""
End-to-end happy-path integration test for the GPS event pipeline.

This test verifies the full real infrastructure path:

sample JSONL
-> RabbitMQ producer
-> real RabbitMQ queue
-> RabbitMQ consumer
-> process_gps_payload
-> validation
-> transformation
-> OracleGpsRepository
-> Oracle PL/SQL package
-> gps rows inserted
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import cast

import oracledb
import pika
import pytest

from app.consumer import consume_json_events_until
from app.event_processor import ProcessingResult, ProcessingStatus, process_gps_payload
from app.oracle_repository import OracleGpsRepository
from app.producer import publish_jsonl_events
from app.rabbitmq_config import RabbitMqConfig


pytestmark = [
    pytest.mark.integration,
    pytest.mark.rabbitmq,
    pytest.mark.oracle,
]


JsonObject = dict[str, object]
OracleEventIdentity = tuple[str, str]


def _make_queue_name() -> str:
    return f"gps_events_e2e_{uuid.uuid4().hex}"


def _make_external_event_id(run_id: str, index: int) -> str:
    return f"gps-e2e-{run_id}-{index}"


def _make_test_rabbitmq_config(
    base_config: RabbitMqConfig,
    *,
    queue_name: str,
) -> RabbitMqConfig:
    return RabbitMqConfig(
        host=base_config.host,
        port=base_config.port,
        username=base_config.username,
        password=base_config.password,
        queue_name=queue_name,
    )


def _open_rabbitmq_connection(config: RabbitMqConfig) -> pika.BlockingConnection:
    credentials = pika.PlainCredentials(config.username, config.password)
    parameters = pika.ConnectionParameters(
        host=config.host,
        port=config.port,
        credentials=credentials,
    )
    return pika.BlockingConnection(parameters)


def _prepare_rabbitmq_queue(config: RabbitMqConfig) -> None:
    connection = _open_rabbitmq_connection(config)

    try:
        channel = connection.channel()  # pyright: ignore[reportUnknownMemberType]
        channel.queue_declare(queue=config.queue_name, durable=True)  # pyright: ignore[reportUnknownMemberType]
        channel.queue_purge(queue=config.queue_name)  # pyright: ignore[reportUnknownMemberType]
    finally:
        connection.close()


def _delete_rabbitmq_queue(config: RabbitMqConfig) -> None:
    connection = _open_rabbitmq_connection(config)

    try:
        channel = connection.channel()  # pyright: ignore[reportUnknownMemberType]
        channel.queue_purge(queue=config.queue_name)  # pyright: ignore[reportUnknownMemberType]
        channel.queue_delete(queue=config.queue_name)  # pyright: ignore[reportUnknownMemberType]
    finally:
        connection.close()


def _open_oracle_connection() -> oracledb.Connection:
    return oracledb.connect(
        user=_required_env("LOGISTICS_DB_USER"),
        password=_required_env("LOGISTICS_DB_PASSWORD"),
        dsn=_required_env("ORACLE_DSN"),
    )


def _required_env(name: str) -> str:
    value = os.environ.get(name)

    if not value:
        raise RuntimeError(f"Required environment variable is not set: {name}")

    return value


def _fetch_gps_row_count(
    connection: oracledb.Connection,
    *,
    source_system: str,
    external_event_id: str,
) -> int:
    with connection.cursor() as cursor:
        cursor.execute( # pyright: ignore[reportUnknownMemberType]
            """
            select count(*)
            from gps
            where source_system = :source_system
              and external_event_id = :external_event_id
            """,
            {
                "source_system": source_system,
                "external_event_id": external_event_id,
            },
        )

        row = cast(tuple[int] | None, cursor.fetchone())

    if row is None:
        return 0

    return row[0]


def _delete_gps_events(
    *,
    identities: list[OracleEventIdentity],
) -> None:
    if not identities:
        return

    connection = _open_oracle_connection()

    try:
        with connection.cursor() as cursor:
            for source_system, external_event_id in identities:
                cursor.execute( # pyright: ignore[reportUnknownMemberType]
                    """
                    delete from gps
                    where source_system = :source_system
                      and external_event_id = :external_event_id
                    """,
                    {
                        "source_system": source_system,
                        "external_event_id": external_event_id,
                    },
                )

        connection.commit()
    finally:
        connection.close()


def _load_sample_events(limit: int) -> list[JsonObject]:
    sample_jsonl_path = Path("sample_data/incoming_events.jsonl")

    events: list[JsonObject] = []

    with sample_jsonl_path.open("r", encoding="utf-8") as file:
        for line in file:
            if len(events) >= limit:
                break

            parsed_event = cast(JsonObject, json.loads(line))
            events.append(parsed_event)

    return events


def _write_unique_jsonl_events(
    *,
    tmp_path: Path,
    base_events: list[JsonObject],
    run_id: str,
) -> tuple[Path, list[OracleEventIdentity]]:
    jsonl_path = tmp_path / "incoming_events_e2e.jsonl"

    unique_events: list[JsonObject] = []
    identities: list[OracleEventIdentity] = []

    for index, event in enumerate(base_events, start=1):
        unique_event = dict(event)
        external_event_id = _make_external_event_id(run_id, index)
        unique_event["external_event_id"] = external_event_id

        source_system = cast(str, unique_event["source_system"])

        unique_events.append(unique_event)
        identities.append((source_system, external_event_id))

    with jsonl_path.open("w", encoding="utf-8") as file:
        for event in unique_events:
            file.write(json.dumps(event, separators=(",", ":"), sort_keys=True))
            file.write("\n")

    return jsonl_path, identities


def test_sample_jsonl_to_rabbitmq_consumer_to_oracle_happy_path(
    tmp_path: Path,
) -> None:
    run_id = uuid.uuid4().hex
    queue_name = _make_queue_name()

    base_rabbitmq_config = RabbitMqConfig.from_env()
    rabbitmq_config = _make_test_rabbitmq_config(
        base_rabbitmq_config,
        queue_name=queue_name,
    )

    base_events = _load_sample_events(limit=2)
    temp_jsonl_path, oracle_identities = _write_unique_jsonl_events(
        tmp_path=tmp_path,
        base_events=base_events,
        run_id=run_id,
    )

    results: list[ProcessingResult] = []

    try:
        _prepare_rabbitmq_queue(rabbitmq_config)

        published_count = publish_jsonl_events(temp_jsonl_path, rabbitmq_config)

        assert published_count == 2

        repository = OracleGpsRepository()

        def handle_payload(payload: JsonObject) -> ProcessingResult:
            result = process_gps_payload(payload, repository)
            results.append(result)
            return result

        consumed_count = consume_json_events_until(
            config=rabbitmq_config,
            handler=handle_payload,
            max_messages=published_count,
        )

        assert consumed_count == published_count
        assert len(results) == published_count
        assert all(result.status == ProcessingStatus.INSERTED for result in results)
        assert all(result.success for result in results)
        assert all(result.should_ack for result in results)

        connection = _open_oracle_connection()

        try:
            for source_system, external_event_id in oracle_identities:
                assert (
                    _fetch_gps_row_count(
                        connection,
                        source_system=source_system,
                        external_event_id=external_event_id,
                    )
                    == 1
                )
        finally:
            connection.close()

    finally:
        _delete_gps_events(identities=oracle_identities)
        _delete_rabbitmq_queue(rabbitmq_config)