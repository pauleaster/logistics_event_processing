from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Protocol
from unittest.mock import Mock, patch

import pytest

from app.consumer import (
    JsonObject,
    RabbitMqMessageError,
    _parse_message_body, # pyright: ignore[reportPrivateUsage]
    consume_json_events,
)
from app.rabbitmq_config import RabbitMqConfig


@dataclass(frozen=True)
class StubHandlingResult:
    should_ack: bool


class MessageCallback(Protocol):
    def __call__(
        self,
        channel: object,
        method: object,
        properties: object,
        body: bytes,
    ) -> None:
        ...


def test_parse_message_body_returns_json_object() -> None:
    payload = _parse_message_body(
        b'{"event_type": "GPS_CRUMB", "external_event_id": "evt-001"}'
    )

    assert payload == {
        "event_type": "GPS_CRUMB",
        "external_event_id": "evt-001",
    }


def test_parse_message_body_rejects_malformed_json() -> None:
    with pytest.raises(RabbitMqMessageError, match="not valid JSON"):
        _parse_message_body(b'{"event_type": "GPS_CRUMB"')


@pytest.mark.parametrize(
    "body",
    [
        b'["not", "an", "object"]',
        b'"not an object"',
        b"123",
        b"true",
        b"null",
    ],
)
def test_parse_message_body_rejects_non_object_json(body: bytes) -> None:
    with pytest.raises(RabbitMqMessageError, match="must be a JSON object"):
        _parse_message_body(body)


def test_parse_message_body_rejects_non_utf8_body() -> None:
    with pytest.raises(RabbitMqMessageError, match="not valid UTF-8"):
        _parse_message_body(b"\xff\xfe\xfd")


def test_consume_json_events_declares_queue_and_registers_consumer() -> None:
    config = _make_config()
    channel = Mock()
    connection = Mock()
    connection.channel.return_value = channel
    connection.is_open = True

    with patch("app.consumer.pika.BlockingConnection", return_value=connection):
        consume_json_events(config=config, handler=lambda payload: StubHandlingResult(True))

    channel.queue_declare.assert_called_once_with(queue=config.queue_name, durable=True)
    channel.basic_consume.assert_called_once()

    basic_consume_kwargs = channel.basic_consume.call_args.kwargs
    assert basic_consume_kwargs["queue"] == config.queue_name
    assert basic_consume_kwargs["auto_ack"] is False
    assert callable(basic_consume_kwargs["on_message_callback"])

    channel.start_consuming.assert_called_once_with()
    connection.close.assert_called_once_with()


def test_consumer_acknowledges_when_handler_result_should_ack() -> None:
    handler_payloads: list[JsonObject] = []

    def handler(payload: JsonObject) -> StubHandlingResult:
        handler_payloads.append(payload)
        return StubHandlingResult(should_ack=True)

    callback, channel = _registered_callback(handler)

    callback(
        channel,
        SimpleNamespace(delivery_tag=123),
        object(),
        b'{"external_event_id": "evt-001"}',
    )

    assert handler_payloads == [{"external_event_id": "evt-001"}]
    channel.basic_ack.assert_called_once_with(delivery_tag=123)
    channel.basic_reject.assert_not_called()


def test_consumer_rejects_when_handler_result_should_not_ack() -> None:
    def handler(payload: JsonObject) -> StubHandlingResult:
        return StubHandlingResult(should_ack=False)

    callback, channel = _registered_callback(handler)

    callback(
        channel,
        SimpleNamespace(delivery_tag=456),
        object(),
        b'{"external_event_id": "evt-002"}',
    )

    channel.basic_ack.assert_not_called()
    channel.basic_reject.assert_called_once_with(delivery_tag=456, requeue=False)


def test_consumer_rejects_malformed_json_without_calling_handler() -> None:
    handler = Mock(return_value=StubHandlingResult(should_ack=True))
    callback, channel = _registered_callback(handler)

    callback(
        channel,
        SimpleNamespace(delivery_tag=789),
        object(),
        b'{"broken": ',
    )

    handler.assert_not_called()
    channel.basic_ack.assert_not_called()
    channel.basic_reject.assert_called_once_with(delivery_tag=789, requeue=False)


def test_consumer_rejects_non_object_json_without_calling_handler() -> None:
    handler = Mock(return_value=StubHandlingResult(should_ack=True))
    callback, channel = _registered_callback(handler)

    callback(
        channel,
        SimpleNamespace(delivery_tag=790),
        object(),
        b'["not", "an", "object"]',
    )

    handler.assert_not_called()
    channel.basic_ack.assert_not_called()
    channel.basic_reject.assert_called_once_with(delivery_tag=790, requeue=False)


def test_consumer_rejects_when_handler_raises() -> None:
    def handler(payload: JsonObject) -> StubHandlingResult:
        raise RuntimeError("unexpected handler failure")

    callback, channel = _registered_callback(handler)

    callback(
        channel,
        SimpleNamespace(delivery_tag=791),
        object(),
        b'{"external_event_id": "evt-003"}',
    )

    channel.basic_ack.assert_not_called()
    channel.basic_reject.assert_called_once_with(delivery_tag=791, requeue=False)


def _registered_callback(
    handler: Callable[[JsonObject], StubHandlingResult],
) -> tuple[MessageCallback, Mock]:
    config = _make_config()
    channel = Mock()
    connection = Mock()
    connection.channel.return_value = channel
    connection.is_open = True

    with patch("app.consumer.pika.BlockingConnection", return_value=connection):
        consume_json_events(config=config, handler=handler)

    callback = channel.basic_consume.call_args.kwargs["on_message_callback"]
    return callback, channel


def _make_config() -> RabbitMqConfig:
    return RabbitMqConfig(
        host="localhost",
        port=5672,
        username="guest",
        password="guest",
        queue_name="gps-events",
    )