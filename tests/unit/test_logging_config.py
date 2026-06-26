import json
import logging
from datetime import datetime, timezone
from typing import Any, TypeAlias
from pytest import LogCaptureFixture

from app.logging_config import (
    JsonLogFormatter,
    log_event_received,
    log_event_rejected,
    make_event_hash,
    make_event_log_extra,
)


GpsPayload: TypeAlias = dict[str, Any]


def valid_payload() -> GpsPayload:
    return {
        "source_system": "DRIVER_APP",
        "external_event_id": "gps-000001",
        "event_type": "GPS_CRUMB",
        "event_timestamp": "2026-06-26T03:15:00+00:00",
        "driver_code": "DRV001",
        "vehicle_code": "VH-001",
        "latitude": -38.123,
        "longitude": 145.123,
        "speed_kmh": 42.5,
        "heading_degrees": 87,
        "gps_accuracy_m": 8.5,
        "battery_level_percent": 76,
    }


def test_make_event_hash_is_deterministic_for_same_event_identity() -> None:
    payload = valid_payload()

    first_hash = make_event_hash(payload)
    second_hash = make_event_hash(payload)

    assert first_hash == second_hash
    assert len(first_hash) == 16


def test_make_event_hash_ignores_non_identity_payload_fields() -> None:
    first_payload = valid_payload()
    second_payload: GpsPayload = {
        **valid_payload(),
        "latitude": -37.999,
        "longitude": 144.999,
        "speed_kmh": 80,
    }

    assert make_event_hash(first_payload) == make_event_hash(second_payload)


def test_make_event_hash_changes_when_identity_field_changes() -> None:
    first_payload = valid_payload()
    second_payload: GpsPayload = {
        **valid_payload(),
        "external_event_id": "gps-000002",
    }

    assert make_event_hash(first_payload) != make_event_hash(second_payload)


def test_make_event_hash_accepts_datetime_values() -> None:
    first_payload: GpsPayload = {
        **valid_payload(),
        "event_timestamp": datetime(2026, 6, 26, 3, 15, tzinfo=timezone.utc),
    }

    second_payload: GpsPayload = {
        **valid_payload(),
        "event_timestamp": datetime(2026, 6, 26, 3, 15, tzinfo=timezone.utc),
    }

    assert make_event_hash(first_payload) == make_event_hash(second_payload)


def test_make_event_log_extra_contains_expected_structured_fields() -> None:
    payload = valid_payload()

    extra = make_event_log_extra(
        payload,
        stage="validation",
        status="accepted",
    )

    assert extra["event_hash"] == make_event_hash(payload)
    assert extra["source_system"] == "DRIVER_APP"
    assert extra["external_event_id"] == "gps-000001"
    assert extra["event_type"] == "GPS_CRUMB"
    assert extra["driver_code"] == "DRV001"
    assert extra["vehicle_code"] == "VH-001"
    assert extra["stage"] == "validation"
    assert extra["status"] == "accepted"
    assert extra["error_type"] is None
    assert extra["error_message"] is None


def test_log_event_received_emits_structured_record(caplog: LogCaptureFixture) -> None:
    payload = valid_payload()
    logger = logging.getLogger("test.gps.received")

    with caplog.at_level(logging.INFO, logger=logger.name):
        log_event_received(payload, logger=logger)

    assert len(caplog.records) == 1

    record: logging.LogRecord = caplog.records[0]

    assert record.message == "gps_event_received"
    assert getattr(record, "event_hash") == make_event_hash(payload)
    assert getattr(record, "source_system") == "DRIVER_APP"
    assert getattr(record, "external_event_id") == "gps-000001"
    assert getattr(record, "stage") == "received"
    assert getattr(record, "status") == "received"
    assert getattr(record, "error_type") is None
    assert getattr(record, "error_message") is None


def test_log_event_rejected_emits_structured_record(caplog: LogCaptureFixture) -> None:
    payload = valid_payload()
    logger = logging.getLogger("test.gps.rejected")
    error = ValueError("invalid GPS payload")

    with caplog.at_level(logging.WARNING, logger=logger.name):
        log_event_rejected(
            payload,
            stage="validation",
            error=error,
            logger=logger,
        )

    assert len(caplog.records) == 1

    record: logging.LogRecord = caplog.records[0]

    assert record.message == "gps_event_rejected"
    assert getattr(record, "event_hash") == make_event_hash(payload)
    assert getattr(record, "stage") == "validation"
    assert getattr(record, "status") == "rejected"
    assert getattr(record, "error_type") == "ValueError"
    assert getattr(record, "error_message") == "invalid GPS payload"


def test_json_log_formatter_outputs_valid_json() -> None:
    payload = valid_payload()
    record = logging.LogRecord(
        name="test.gps.formatter",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="gps_event_received",
        args=(),
        exc_info=None,
    )

    for key, value in make_event_log_extra(
        payload,
        stage="received",
        status="received",
    ).items():
        setattr(record, key, value)

    formatter = JsonLogFormatter()
    formatted = formatter.format(record)

    parsed = json.loads(formatted)

    assert parsed["message"] == "gps_event_received"
    assert parsed["level"] == "INFO"
    assert parsed["event_hash"] == make_event_hash(payload)
    assert parsed["source_system"] == "DRIVER_APP"
    assert parsed["status"] == "received"