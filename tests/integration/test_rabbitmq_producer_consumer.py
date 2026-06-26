"""
RabbitMQ producer-to-consumer integration tests.

These tests require a running RabbitMQ container.

Expected setup from the project root:

    docker start logistics-rabbitmq

Run this test file with:

    pytest tests/integration/test_rabbitmq_producer_consumer.py -m "integration and rabbitmq" -v

This test verifies only the RabbitMQ transport path:

    producer -> RabbitMQ queue -> consumer -> handler

It deliberately does not call Oracle and does not validate GPS payloads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

import pika
import pytest

from app.consumer import consume_json_events_until
from app.producer import publish_jsonl_events
from app.rabbitmq_config import RabbitMqConfig


JsonObject = dict[str, object]


@dataclass(frozen=True, slots=True)
class FakeHandlingResult:
    should_ack: bool = True


def _connection_parameters(config: RabbitMqConfig) -> pika.ConnectionParameters:
    credentials = pika.PlainCredentials(config.username, config.password)
    return pika.ConnectionParameters(
        host=config.host,
        port=config.port,
        credentials=credentials,
    )


def _write_jsonl(path: Path, events: list[JsonObject]) -> None:
    lines = [json.dumps(event, separators=(",", ":"), sort_keys=True) for event in events]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.integration
@pytest.mark.rabbitmq
def test_producer_publishes_messages_that_consumer_receives_and_acks(
    tmp_path: Path,
) -> None:
    base_config = RabbitMqConfig.from_env()
    queue_name = f"gps_events_it_{uuid4().hex}"

    config = RabbitMqConfig(
        host=base_config.host,
        port=base_config.port,
        username=base_config.username,
        password=base_config.password,
        queue_name=queue_name,
    )

    parameters = _connection_parameters(config)
    setup_connection = pika.BlockingConnection(parameters)

    try:
        setup_channel = setup_connection.channel()
        setup_channel.queue_declare(  # pyright: ignore[reportUnknownMemberType]
            queue=queue_name,
            durable=True,
        )
        setup_channel.queue_purge(queue=queue_name)  # pyright: ignore[reportUnknownMemberType]

        events: list[JsonObject] = [
            {
                "event_type": "GPS_CRUMB",
                "source_system": "DRIVER_APP",
                "external_event_id": "evt-it-001",
                "event_timestamp": "2026-06-26T06:00:00Z",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "latitude": -38.12345,
                "longitude": 145.12345,
                "speed_kmh": 82.5,
                "heading_degrees": 180,
                "gps_accuracy_m": 4.2,
                "battery_level_percent": 87,
            },
            {
                "event_type": "GPS_CRUMB",
                "source_system": "DRIVER_APP",
                "external_event_id": "evt-it-002",
                "event_timestamp": "2026-06-26T06:01:00Z",
                "driver_code": "DRV002",
                "vehicle_code": "VEH002",
                "latitude": -38.22345,
                "longitude": 145.22345,
                "speed_kmh": 64.0,
                "heading_degrees": 90,
                "gps_accuracy_m": 5.1,
                "battery_level_percent": 76,
            },
        ]

        jsonl_path = tmp_path / "events.jsonl"
        _write_jsonl(jsonl_path, events)

        published_count = publish_jsonl_events(jsonl_path, config)

        received_payloads: list[JsonObject] = []

        def handler(payload: JsonObject) -> FakeHandlingResult:
            received_payloads.append(payload)
            return FakeHandlingResult(should_ack=True)

        consumed_count = consume_json_events_until(
            config=config,
            handler=handler,
            max_messages=len(events),
        )

        assert published_count == len(events)
        assert consumed_count == len(events)
        assert received_payloads == events

        queue_state = cast(
            object,
            setup_channel.queue_declare(  # pyright: ignore[reportUnknownMemberType]
                queue=queue_name,
                durable=True,
                passive=True,
            ),
        )

        queue_state_method = cast(object, getattr(queue_state, "method", None))
        message_count = cast(int, getattr(queue_state_method, "message_count", 0))
        assert message_count == 0

    finally:
        cleanup_channel = setup_connection.channel()
        cleanup_channel.queue_purge(queue=queue_name)  # pyright: ignore[reportUnknownMemberType]
        cleanup_channel.queue_delete(queue=queue_name)  # pyright: ignore[reportUnknownMemberType]
        setup_connection.close()