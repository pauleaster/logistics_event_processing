"""
Structured logging helpers for GPS event processing.

This module intentionally uses only Python's standard logging library.
It provides:

- JSON log formatting
- deterministic event hashes for correlation
- helper functions for accepted and rejected GPS event logs

The event hash is based on stable event identity fields rather than the full
raw payload. This avoids repeatedly logging the entire inbound event while still
allowing related log lines to be correlated.
"""

import hashlib
import json
import logging
import sys
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast


GPS_EVENT_LOGGER_NAME = "app.gps_events"


EVENT_IDENTITY_FIELDS = (
    "source_system",
    "external_event_id",
    "event_type",
    "event_timestamp",
    "driver_code",
    "vehicle_code",
)


STRUCTURED_LOG_FIELDS = (
    "event_hash",
    "source_system",
    "external_event_id",
    "event_type",
    "driver_code",
    "vehicle_code",
    "stage",
    "status",
    "error_type",
    "error_message",
)


class JsonLogFormatter(logging.Formatter):
    """Small JSON formatter for structured application logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
            ).astimezone().isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for field_name in STRUCTURED_LOG_FIELDS:
            log_data[field_name] = getattr(record, field_name, None)

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=_json_default, sort_keys=True)


def configure_logging(level: int = logging.INFO) -> None:
    """
    Configure application logging.

    Uses force=True so repeated test/local invocations do not duplicate handlers.
    """

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())

    logging.basicConfig(
        level=level,
        handlers=[handler],
        force=True,
    )

    logging.getLogger("pika").setLevel(logging.WARNING)


def get_gps_event_logger() -> logging.Logger:
    """Return the logger used for GPS event lifecycle logs."""

    return logging.getLogger(GPS_EVENT_LOGGER_NAME)


def make_event_hash(payload_or_event: Any) -> str:
    """
    Build a deterministic hash from stable GPS event identity fields.

    The hash intentionally excludes high-volume telemetry fields such as latitude,
    longitude, speed, heading, and raw payload content.
    """

    identity = {
        field_name: _normalise_value(_extract_field(payload_or_event, field_name))
        for field_name in EVENT_IDENTITY_FIELDS
    }

    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def make_event_log_extra(
    payload_or_event: Any,
    *,
    stage: str,
    status: str,
    error_type: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Create the structured `extra` dict used by logging calls."""

    return {
        "event_hash": make_event_hash(payload_or_event),
        "source_system": _extract_field(payload_or_event, "source_system"),
        "external_event_id": _extract_field(payload_or_event, "external_event_id"),
        "event_type": _extract_field(payload_or_event, "event_type"),
        "driver_code": _extract_field(payload_or_event, "driver_code"),
        "vehicle_code": _extract_field(payload_or_event, "vehicle_code"),
        "stage": stage,
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
    }


def log_event_received(
    payload_or_event: Any,
    *,
    logger: logging.Logger | None = None,
) -> None:
    """Log that a GPS event payload has been received."""

    active_logger = logger or get_gps_event_logger()
    active_logger.info(
        "gps_event_received",
        extra=make_event_log_extra(
            payload_or_event,
            stage="received",
            status="received",
        ),
    )


def log_event_validated(
    payload_or_event: Any,
    *,
    logger: logging.Logger | None = None,
) -> None:
    """Log that a GPS event has passed validation."""

    active_logger = logger or get_gps_event_logger()
    active_logger.info(
        "gps_event_validated",
        extra=make_event_log_extra(
            payload_or_event,
            stage="validation",
            status="accepted",
        ),
    )


def log_event_transformed(
    payload_or_event: Any,
    *,
    logger: logging.Logger | None = None,
) -> None:
    """Log that a GPS event has been transformed into its persistence shape."""

    active_logger = logger or get_gps_event_logger()
    active_logger.info(
        "gps_event_transformed",
        extra=make_event_log_extra(
            payload_or_event,
            stage="transformation",
            status="accepted",
        ),
    )


def log_event_inserted(
    payload_or_event: Any,
    *,
    logger: logging.Logger | None = None,
) -> None:
    """Log that a GPS event has been inserted into Oracle."""

    active_logger = logger or get_gps_event_logger()
    active_logger.info(
        "gps_event_inserted",
        extra=make_event_log_extra(
            payload_or_event,
            stage="oracle_insert",
            status="inserted",
        ),
    )


def log_event_rejected(
    payload_or_event: Any,
    *,
    stage: str,
    error: Exception,
    logger: logging.Logger | None = None,
) -> None:
    """
    Log that a GPS event was rejected.

    This function does not decide whether to reject the event. It only records
    the rejection once the caller has made that decision.
    """

    active_logger = logger or get_gps_event_logger()
    active_logger.warning(
        "gps_event_rejected",
        extra=make_event_log_extra(
            payload_or_event,
            stage=stage,
            status="rejected",
            error_type=type(error).__name__,
            error_message=str(error),
        ),
    )


def log_event_database_error(
    payload_or_event: Any,
    *,
    error: Exception,
    logger: logging.Logger | None = None,
) -> None:
    """
    Log a database error for a GPS event.

    Step 17 can decide the broader retry/rejection/error-handling behaviour.
    This helper only records the event-correlated database failure.
    """

    active_logger = logger or get_gps_event_logger()
    active_logger.error(
        "gps_event_database_error",
        extra=make_event_log_extra(
            payload_or_event,
            stage="oracle_insert",
            status="failed",
            error_type=type(error).__name__,
            error_message=str(error),
        ),
    )


def _extract_field(payload_or_event: Any, field_name: str) -> Any:
    """Extract a field from either a dict-like payload or an object/model."""

    if isinstance(payload_or_event, Mapping):
        payload_mapping = cast(Mapping[str, Any], payload_or_event)
        return payload_mapping.get(field_name)

    return getattr(payload_or_event, field_name, None)


def _normalise_value(value: Any) -> Any:
    """Normalise values so hashing is deterministic across equivalent inputs."""

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    return value


def _json_default(value: Any) -> str:
    """Fallback JSON serialiser for log output."""

    if isinstance(value, datetime | date):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    return str(value)