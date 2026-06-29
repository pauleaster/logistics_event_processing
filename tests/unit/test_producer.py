from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, cast
from unittest.mock import Mock, patch

import pytest

import app.producer as producer_module
from app.producer import (
    JsonlEventError,
    Producer,
    publish_jsonl_events,
    read_jsonl_events,
)
from app.rabbitmq_config import RabbitMqConfig


JsonObject = dict[str, object]


class _ProducerWithPublishEvents(Protocol):
    def publish_events(self, events: JsonObject | list[JsonObject]) -> int:
        ...


@pytest.fixture
def rabbitmq_config() -> RabbitMqConfig:
    return RabbitMqConfig(
        host="localhost",
        port=5672,
        username="guest",
        password="guest",
        queue_name="gps_events",
    )


def test_read_jsonl_events_skips_empty_lines(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "events.jsonl"
    jsonl_path.write_text(
        "\n"
        '{"external_event_id": "gps-001"}\n'
        "   \n"
        '{"external_event_id": "gps-002"}\n',
        encoding="utf-8",
    )

    events = list(read_jsonl_events(jsonl_path))

    assert events == [
        {"external_event_id": "gps-001"},
        {"external_event_id": "gps-002"},
    ]


def test_read_jsonl_events_raises_clear_error_for_malformed_json(
    tmp_path: Path,
) -> None:
    jsonl_path = tmp_path / "events.jsonl"
    jsonl_path.write_text(
        '{"external_event_id": "gps-001"}\n'
        '{"external_event_id": }\n',
        encoding="utf-8",
    )

    with pytest.raises(JsonlEventError, match="Malformed JSON.*line 2"):
        list(read_jsonl_events(jsonl_path))


def test_read_jsonl_events_raises_clear_error_for_non_object_json(
    tmp_path: Path,
) -> None:
    jsonl_path = tmp_path / "events.jsonl"
    jsonl_path.write_text(
        '["not", "an", "object"]\n',
        encoding="utf-8",
    )

    with pytest.raises(JsonlEventError, match="Expected JSON object.*line 1"):
        list(read_jsonl_events(jsonl_path))


@patch("app.producer.pika.BlockingConnection")
def test_producer_publish_jsonl_events_declares_durable_queue_and_publishes_messages(
    blocking_connection_mock: Mock,
    tmp_path: Path,
    rabbitmq_config: RabbitMqConfig,
) -> None:
    jsonl_path = tmp_path / "events.jsonl"
    jsonl_path.write_text(
        '{"external_event_id": "gps-001", "source_system": "DRIVER_APP"}\n'
        "\n"
        '{"external_event_id": "gps-002", "source_system": "DRIVER_APP"}\n',
        encoding="utf-8",
    )

    connection_mock = Mock()
    channel_mock = Mock()

    blocking_connection_mock.return_value = connection_mock
    connection_mock.channel.return_value = channel_mock

    producer = Producer(rabbitmq_config)
    published_count = producer.publish_jsonl_events(jsonl_path=jsonl_path)

    assert published_count == 2

    channel_mock.queue_declare.assert_called_once_with(
        queue="gps_events",
        durable=True,
    )

    assert channel_mock.basic_publish.call_count == 2

    first_call = channel_mock.basic_publish.call_args_list[0]
    second_call = channel_mock.basic_publish.call_args_list[1]

    assert first_call.kwargs["exchange"] == ""
    assert first_call.kwargs["routing_key"] == "gps_events"
    assert json.loads(first_call.kwargs["body"].decode("utf-8")) == {
        "external_event_id": "gps-001",
        "source_system": "DRIVER_APP",
    }

    assert second_call.kwargs["exchange"] == ""
    assert second_call.kwargs["routing_key"] == "gps_events"
    assert json.loads(second_call.kwargs["body"].decode("utf-8")) == {
        "external_event_id": "gps-002",
        "source_system": "DRIVER_APP",
    }

    connection_mock.close.assert_called_once_with()


def test_publish_jsonl_events_wrapper_delegates_to_producer_class(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rabbitmq_config: RabbitMqConfig,
) -> None:
    jsonl_path = tmp_path / "events.jsonl"
    jsonl_path.write_text('{"external_event_id": "gps-001"}\n', encoding="utf-8")

    producer_mock = Mock()
    producer_mock.publish_jsonl_events.return_value = 123

    producer_class_mock = Mock(return_value=producer_mock)
    monkeypatch.setattr(producer_module, "Producer", producer_class_mock)

    published_count = publish_jsonl_events(
        jsonl_path=jsonl_path,
        config=rabbitmq_config,
    )

    assert published_count == 123
    producer_class_mock.assert_called_once_with(rabbitmq_config)
    producer_mock.publish_jsonl_events.assert_called_once_with(jsonl_path)


@patch("app.producer.pika.BlockingConnection")
def test_publish_jsonl_events_does_not_connect_when_jsonl_is_malformed(
    blocking_connection_mock: Mock,
    tmp_path: Path,
    rabbitmq_config: RabbitMqConfig,
) -> None:
    jsonl_path = tmp_path / "events.jsonl"
    jsonl_path.write_text(
        '{"external_event_id": "gps-001"}\n'
        '{"external_event_id": }\n',
        encoding="utf-8",
    )

    with pytest.raises(JsonlEventError, match="Malformed JSON.*line 2"):
        publish_jsonl_events(
            jsonl_path=jsonl_path,
            config=rabbitmq_config,
        )

    blocking_connection_mock.assert_not_called()


@patch("app.producer.pika.BlockingConnection")
def test_producer_publish_events_publishes_single_event(
    blocking_connection_mock: Mock,
    rabbitmq_config: RabbitMqConfig,
) -> None:
    connection_mock = Mock()
    channel_mock = Mock()

    blocking_connection_mock.return_value = connection_mock
    connection_mock.channel.return_value = channel_mock

    producer = Producer(rabbitmq_config)

    event: JsonObject = {
        "external_event_id": "gps-001",
        "source_system": "DRIVER_APP",
    }

    published_count = cast(_ProducerWithPublishEvents, producer).publish_events(event)

    assert published_count == 1

    channel_mock.queue_declare.assert_called_once_with(
        queue="gps_events",
        durable=True,
    )

    channel_mock.basic_publish.assert_called_once()

    first_call = channel_mock.basic_publish.call_args_list[0]
    assert first_call.kwargs["exchange"] == ""
    assert first_call.kwargs["routing_key"] == "gps_events"
    assert json.loads(first_call.kwargs["body"].decode("utf-8")) == event

    connection_mock.close.assert_called_once_with()


@patch("app.producer.pika.BlockingConnection")
def test_producer_publish_events_publishes_multiple_events(
    blocking_connection_mock: Mock,
    rabbitmq_config: RabbitMqConfig,
) -> None:
    connection_mock = Mock()
    channel_mock = Mock()

    blocking_connection_mock.return_value = connection_mock
    connection_mock.channel.return_value = channel_mock

    producer = Producer(rabbitmq_config)

    events: list[JsonObject] = [
        {
            "external_event_id": "gps-001",
            "source_system": "DRIVER_APP",
        },
        {
            "external_event_id": "gps-002",
            "source_system": "DRIVER_APP",
        },
    ]

    published_count = cast(_ProducerWithPublishEvents, producer).publish_events(events)

    assert published_count == 2

    channel_mock.queue_declare.assert_called_once_with(
        queue="gps_events",
        durable=True,
    )

    assert channel_mock.basic_publish.call_count == 2

    first_call = channel_mock.basic_publish.call_args_list[0]
    second_call = channel_mock.basic_publish.call_args_list[1]

    assert first_call.kwargs["exchange"] == ""
    assert first_call.kwargs["routing_key"] == "gps_events"
    assert second_call.kwargs["exchange"] == ""
    assert second_call.kwargs["routing_key"] == "gps_events"

    assert json.loads(first_call.kwargs["body"].decode("utf-8")) == events[0]
    assert json.loads(second_call.kwargs["body"].decode("utf-8")) == events[1]

    connection_mock.close.assert_called_once_with()
