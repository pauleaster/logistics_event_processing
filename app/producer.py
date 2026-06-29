"""
RabbitMQ producer for JSONL GPS event payloads.

The producer is intentionally narrow:

- read JSONL events from disk
- parse each non-empty line as JSON
- publish one JSON object per RabbitMQ message

It does not validate GPS events, transform records, call Oracle, or consume
messages. Those responsibilities belong to later pipeline stages.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import cast

import pika

from app.rabbitmq_config import RabbitMqConfig


JsonObject = dict[str, object]


class JsonlEventError(ValueError):
    """Raised when a JSONL file contains a malformed or non-object event line."""


class Producer:
    """RabbitMQ publisher for JSONL event payloads."""

    def __init__(self, config: RabbitMqConfig) -> None:
        self._config = config

    def publish_jsonl_events(self, jsonl_path: Path) -> int:
        """
        Publish each JSON object in a JSONL file to RabbitMQ.

        Empty lines are skipped.

        The file is parsed before connecting to RabbitMQ. This avoids partially
        publishing a file where a later line is malformed.

        Returns:
            Number of messages published.

        Raises:
            FileNotFoundError: if jsonl_path does not exist.
            JsonlEventError: if a non-empty line is invalid JSON or not a JSON object.
            pika.exceptions.AMQPError: for RabbitMQ connection/publish failures.
        """

        events = list(read_jsonl_events(jsonl_path))
        return self.publish_events(events)

    def publish_events(self, events: JsonObject | Iterable[JsonObject]) -> int:
        events_to_publish: list[JsonObject]

        if isinstance(events, dict):
            events_to_publish = [cast(JsonObject, events)]
        else:
            events_to_publish = list(events)

        return self._publish_events(events_to_publish)

    def _publish_events(self, events: list[JsonObject]) -> int:
        config = self._config

        credentials = pika.PlainCredentials(
            username=config.username,
            password=config.password,
        )

        parameters = pika.ConnectionParameters(
            host=config.host,
            port=config.port,
            credentials=credentials,
        )

        connection = pika.BlockingConnection(parameters)

        try:
            channel = connection.channel()

            channel.queue_declare( # pyright: ignore[reportUnknownMemberType]
                queue=config.queue_name,
                durable=True,
            )

            published_count = 0

            for event in events:
                message_body = json.dumps(
                    event,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")

                channel.basic_publish(
                    exchange="",
                    routing_key=config.queue_name,
                    body=message_body,
                    properties=pika.BasicProperties(delivery_mode=2),
                )

                published_count += 1

            return published_count

        finally:
            connection.close()


def publish_jsonl_events(
    jsonl_path: Path,
    config: RabbitMqConfig,
) -> int:
    """Compatibility wrapper around Producer.publish_jsonl_events."""

    return Producer(config).publish_jsonl_events(jsonl_path)


def read_jsonl_events(jsonl_path: Path) -> Iterator[JsonObject]:
    """
    Yield JSON objects from a JSONL file.

    This function performs syntax-level JSON checking only. It deliberately does
    not validate event_type, GPS fields, driver codes, vehicle codes, or any
    domain-specific constraints.
    """

    with jsonl_path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()

            if line == "":
                continue

            yield _parse_jsonl_line(
                line=line,
                jsonl_path=jsonl_path,
                line_number=line_number,
            )


def _parse_jsonl_line(
    *,
    line: str,
    jsonl_path: Path,
    line_number: int,
) -> JsonObject:
    try:
        parsed_json: object = json.loads(line)
    except json.JSONDecodeError as exc:
        raise JsonlEventError(
            f"Malformed JSON in {jsonl_path} at line {line_number}: {exc.msg}"
        ) from exc

    if not isinstance(parsed_json, dict):
        raise JsonlEventError(
            f"Expected JSON object in {jsonl_path} at line {line_number}, "
            f"got {type(parsed_json).__name__}"
        )

    return cast(JsonObject, parsed_json)


def main() -> None:
    jsonl_path = Path("sample_data/incoming_events.jsonl")
    config = RabbitMqConfig.from_env()

    published_count = publish_jsonl_events(
        jsonl_path=jsonl_path,
        config=config,
    )

    print(f"Published {published_count} message(s) to queue {config.queue_name!r}")


if __name__ == "__main__":
    main()