"""
RabbitMQ configuration helpers.

This module intentionally contains configuration only. Producer and consumer
logic should live in their own modules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RabbitMqConfig:
    """
    Connection settings for the local RabbitMQ instance.

    Defaults are suitable for the official RabbitMQ Docker image using the
    default guest account on localhost.
    """

    host: str
    port: int
    username: str
    password: str
    queue_name: str

    @classmethod
    def from_env(cls) -> RabbitMqConfig:
        return cls(
            host=os.getenv("RABBITMQ_HOST", "localhost"),
            port=_read_int_env("RABBITMQ_PORT", 5672),
            username=os.getenv("RABBITMQ_USER", "guest"),
            password=os.getenv("RABBITMQ_PASSWORD", "guest"),
            queue_name=os.getenv("RABBITMQ_QUEUE", "gps_events"),
        )


def _read_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)

    if raw_value is None or raw_value.strip() == "":
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw_value!r}") from exc