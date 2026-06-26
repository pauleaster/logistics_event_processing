"""
RabbitMQ JSON event consumer.

This module is intentionally transport-focused only.

It is responsible for:
- connecting to RabbitMQ
- declaring/using the configured queue_name
- consuming messages
- decoding message bodies
- parsing JSON message bodies
- ensuring each message is a JSON object
- passing parsed objects to a handler callback
- acknowledging or rejecting messages based on the handler result

It deliberately does not validate GPS payloads, transform events, or write to Oracle.
Those responsibilities belong to app.event_processor and the repository layer.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Protocol, cast

import pika

from app.rabbitmq_config import RabbitMqConfig

logger = logging.getLogger(__name__)

JsonObject = dict[str, object]


class RabbitMqMessageError(ValueError):
    """Raised when a RabbitMQ message body is not a valid JSON object."""


class MessageHandlingResult(Protocol):
    """Minimal result contract required by the RabbitMQ consumer."""

    @property
    def should_ack(self) -> bool:
        """
        Whether the consumed RabbitMQ message should be acknowledged.

        Ellipsis, written as ..., marks this as a Protocol interface member.
        Implementations provide the actual property value.
        """
        ...


def consume_json_events(
    config: RabbitMqConfig,
    handler: Callable[[JsonObject], MessageHandlingResult],
) -> None:
    """
    Consume JSON object messages from RabbitMQ and pass them to handler.

    Messages with malformed JSON, non-object JSON, or unexpected handler failures
    are rejected without requeue to avoid poison-message loops.
    """

    connection = pika.BlockingConnection(_make_connection_parameters(config))

    try:
        channel = connection.channel()
        channel.queue_declare( # pyright: ignore[reportUnknownMemberType]
            queue=config.queue_name, durable=True
            )

        def on_message(
            channel_: object,
            method: object,
            properties: object,
            body: bytes,
        ) -> None:
            del properties

            delivery_tag = _get_delivery_tag(method)

            try:
                payload = _parse_message_body(body)
            except RabbitMqMessageError:
                logger.exception(
                    "Rejected malformed RabbitMQ message",
                    extra={"delivery_tag": delivery_tag},
                )
                _basic_reject(channel_, delivery_tag=delivery_tag, requeue=False)
                return

            try:
                result = handler(payload)
            except Exception:
                logger.exception(
                    "Rejected RabbitMQ message after unexpected handler failure",
                    extra={"delivery_tag": delivery_tag},
                )
                _basic_reject(channel_, delivery_tag=delivery_tag, requeue=False)
                return

            if result.should_ack:
                _basic_ack(channel_, delivery_tag=delivery_tag)
                return

            logger.warning(
                "Rejected RabbitMQ message because handler did not acknowledge it",
                extra={"delivery_tag": delivery_tag},
            )
            _basic_reject(channel_, delivery_tag=delivery_tag, requeue=False)

        channel.basic_consume( # pyright: ignore[reportUnknownMemberType]
            queue=config.queue_name,
            on_message_callback=on_message,
            auto_ack=False,
        )

        logger.info(
            "Started RabbitMQ consumer",
            extra={
                "rabbitmq_host": config.host,
                "rabbitmq_port": config.port,
                "rabbitmq_queue": config.queue_name,
            },
        )

        channel.start_consuming()
    finally:
        if connection.is_open:
            connection.close()


def consume_json_events_until(
    *,
    config: RabbitMqConfig,
    handler: Callable[[JsonObject], MessageHandlingResult],
    max_messages: int,
) -> int:
    """
    Consume JSON events from RabbitMQ until max_messages have been handled.

    This is a bounded variant of consume_json_events() intended for integration
    tests and controlled batch-style consumption. It uses the same parsing and
    ack/reject policy as the unbounded consumer.
    """
    if max_messages < 1:
        raise ValueError("max_messages must be at least 1")

    credentials = pika.PlainCredentials(config.username, config.password)
    parameters = pika.ConnectionParameters(
        host=config.host,
        port=config.port,
        credentials=credentials,
    )

    connection = pika.BlockingConnection(parameters)

    handled_count = 0

    try:
        channel = connection.channel()
        channel.queue_declare(  # pyright: ignore[reportUnknownMemberType]
            queue=config.queue_name,
            durable=True,
        )

        while handled_count < max_messages:
            raw_get = cast(
                object,
                channel.basic_get(  # pyright: ignore[reportUnknownMemberType]
                    queue=config.queue_name,
                    auto_ack=False,
                ),
            )
            method_frame, _properties, body = cast(
                tuple[object | None, object, bytes],
                raw_get,
            )

            if method_frame is None:
                break

            delivery_tag = _get_delivery_tag(method_frame)

            try:
                payload = _parse_message_body(body)
                result = handler(payload)

                if result.should_ack:
                    _basic_ack(channel, delivery_tag=delivery_tag)
                else:
                    _basic_reject(
                        channel,
                        delivery_tag=delivery_tag,
                        requeue=False,
                    )

            except RabbitMqMessageError:
                _basic_reject(
                    channel,
                    delivery_tag=delivery_tag,
                    requeue=False,
                )
            except Exception:
                logger.exception("Unhandled error while handling RabbitMQ message")
                _basic_reject(
                    channel,
                    delivery_tag=delivery_tag,
                    requeue=False,
                )

            handled_count += 1

        return handled_count

    finally:
        connection.close()


def _parse_message_body(body: bytes) -> JsonObject:
    """
    Decode and parse a RabbitMQ message body as a JSON object.

    The producer publishes one JSON object per message, encoded as bytes.
    """

    try:
        decoded_body = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RabbitMqMessageError("RabbitMQ message body is not valid UTF-8") from exc

    try:
        parsed = json.loads(decoded_body)
    except json.JSONDecodeError as exc:
        raise RabbitMqMessageError("RabbitMQ message body is not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise RabbitMqMessageError("RabbitMQ message body must be a JSON object")

    return cast(JsonObject, parsed)


def _make_connection_parameters(config: RabbitMqConfig) -> pika.ConnectionParameters:
    """
    Build pika connection parameters from shared RabbitMQ config.

    Keep this aligned with app.producer.py.
    """

    credentials = pika.PlainCredentials(
        username=config.username,
        password=config.password,
    )

    return pika.ConnectionParameters(
        host=config.host,
        port=config.port,
        credentials=credentials,
    )


def _get_delivery_tag(method: object) -> int:
    delivery_tag = getattr(method, "delivery_tag", None)

    if not isinstance(delivery_tag, int):
        raise RabbitMqMessageError(
            "RabbitMQ delivery method has no integer delivery_tag"
        )

    return delivery_tag


def _basic_ack(channel: object, *, delivery_tag: int) -> None:
    basic_ack = getattr(channel, "basic_ack")
    basic_ack(delivery_tag=delivery_tag)


def _basic_reject(channel: object, *, delivery_tag: int, requeue: bool) -> None:
    basic_reject = getattr(channel, "basic_reject")
    basic_reject(delivery_tag=delivery_tag, requeue=requeue)


def main() -> None:
    """
    Transport-only smoke consumer.

    Step 20 should replace this handler with:
    consumer -> event_processor -> Oracle repository.
    """

    class AckResult:
        @property
        def should_ack(self) -> bool:
            return True

    def log_only_handler(payload: JsonObject) -> AckResult:
        logger.info(
            "Received RabbitMQ JSON event",
            extra={"payload_keys": sorted(payload.keys())},
        )
        return AckResult()

    config = RabbitMqConfig.from_env()
    consume_json_events(config=config, handler=log_only_handler)


if __name__ == "__main__":
    main()
