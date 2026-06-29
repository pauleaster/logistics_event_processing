"""
RabbitMQ integration test for Producer.publish_events.

This test requires a running RabbitMQ container.

Expected setup from the project root:

    docker start logistics-rabbitmq

Run this test file with:

    pytest tests/integration/test_producer_publish_events.py -m "integration and rabbitmq" -v

This test verifies only the RabbitMQ transport path for producer publishing.
It does not call Oracle and does not run validation or transformation logic.
"""

from __future__ import annotations

import json
from typing import Protocol, cast
from uuid import uuid4

import pika
import pytest

from app.producer import Producer
from app.rabbitmq_config import RabbitMqConfig


JsonObject = dict[str, object]


class _ProducerWithPublishEvents(Protocol):
    def publish_events(self, events: JsonObject | list[JsonObject]) -> int:
        ...


@pytest.mark.integration
@pytest.mark.rabbitmq
def test_producer_publish_events_round_trips_through_rabbitmq() -> None:
    base_config = RabbitMqConfig.from_env()
    queue_name = f"gps_events_publish_events_it_{uuid4().hex}"

    config = RabbitMqConfig(
        host=base_config.host,
        port=base_config.port,
        username=base_config.username,
        password=base_config.password,
        queue_name=queue_name,
    )

    credentials = pika.PlainCredentials(config.username, config.password)
    parameters = pika.ConnectionParameters(
        host=config.host,
        port=config.port,
        credentials=credentials,
    )

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
                "external_event_id": "evt-it-publish-events-001",
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
                "external_event_id": "evt-it-publish-events-002",
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

        producer = Producer(config)
        published_count = cast(_ProducerWithPublishEvents, producer).publish_events(events)

        assert published_count == len(events)

        consumed_payloads: list[JsonObject] = []

        consume_connection = pika.BlockingConnection(parameters)

        try:
            consume_channel = consume_connection.channel()

            for _ in range(len(events)):
                method_frame, _properties, body = cast(
                    tuple[object | None, object | None, bytes | None],
                    consume_channel.basic_get(queue=queue_name, auto_ack=False),
                )

                assert method_frame is not None
                assert body is not None

                consumed_payloads.append(cast(JsonObject, json.loads(body.decode("utf-8"))))

                delivery_tag = cast(int, getattr(method_frame, "delivery_tag"))
                consume_channel.basic_ack(delivery_tag=delivery_tag)

        finally:
            consume_connection.close()

        assert consumed_payloads == events

    finally:
        cleanup_channel = setup_connection.channel()
        cleanup_channel.queue_purge(queue=queue_name)  # pyright: ignore[reportUnknownMemberType]
        cleanup_channel.queue_delete(queue=queue_name)  # pyright: ignore[reportUnknownMemberType]
        setup_connection.close()
