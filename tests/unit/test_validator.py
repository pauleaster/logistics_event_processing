# tests/unit/test_validator.py

from datetime import datetime
from typing import Any, TypeAlias

import pytest
from pydantic import ValidationError

from app.validator import GpsEvent, validate_gps_event


GpsPayload: TypeAlias = dict[str, Any]


def valid_payload() -> GpsPayload:
    return {
        "source_system": "DRIVER_APP",
        "external_event_id": "gps-000001",
        "event_type": "GPS_CRUMB",
        "event_timestamp": "2026-06-24T09:15:30+10:00",
        "driver_code": "DRV1027",
        "vehicle_code": "VH-4412",
        "latitude": -37.813628,
        "longitude": 144.963058,
        "speed_kmh": 42.5,
        "heading_degrees": 87,
        "gps_accuracy_m": 8.5,
        "battery_level_percent": 76,
    }


def test_validate_gps_event_accepts_valid_payload() -> None:
    event = validate_gps_event(valid_payload())

    assert isinstance(event, GpsEvent)
    assert event.source_system == "DRIVER_APP"
    assert event.external_event_id == "gps-000001"
    assert event.event_type == "GPS_CRUMB"
    assert event.driver_code == "DRV1027"
    assert event.vehicle_code == "VH-4412"
    assert event.latitude == -37.813628
    assert event.longitude == 144.963058
    assert event.speed_kmh == 42.5
    assert event.heading_degrees == 87
    assert event.gps_accuracy_m == 8.5
    assert event.battery_level_percent == 76


def test_validate_gps_event_strips_whitespace_from_strings() -> None:
    payload = valid_payload()
    payload.update(
        {
            "source_system": "  DRIVER_APP  ",
            "external_event_id": "  gps-000001  ",
            "driver_code": "  DRV1027  ",
            "vehicle_code": "  VH-4412  ",
        }
    )

    event = validate_gps_event(payload)

    assert event.source_system == "DRIVER_APP"
    assert event.external_event_id == "gps-000001"
    assert event.driver_code == "DRV1027"
    assert event.vehicle_code == "VH-4412"


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("event_type", "ORDER_CREATED"),
        ("source_system", ""),
        ("external_event_id", ""),
        ("driver_code", ""),
        ("vehicle_code", ""),
        ("latitude", -90.1),
        ("latitude", 90.1),
        ("longitude", -180.1),
        ("longitude", 180.1),
        ("speed_kmh", -0.1),
        ("heading_degrees", -1),
        ("heading_degrees", 360),
        ("gps_accuracy_m", -0.1),
        ("battery_level_percent", -1),
        ("battery_level_percent", 101),
    ],
)
def test_validate_gps_event_rejects_invalid_values(
    field_name: str,
    bad_value: object,
) -> None:
    payload = valid_payload()
    payload[field_name] = bad_value

    with pytest.raises(ValidationError):
        validate_gps_event(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("latitude", -90.0),
        ("latitude", 90.0),
        ("longitude", -180.0),
        ("longitude", 180.0),
        ("speed_kmh", 0.0),
        ("heading_degrees", 0),
        ("heading_degrees", 359),
        ("gps_accuracy_m", 0.0),
        ("battery_level_percent", 0),
        ("battery_level_percent", 100),
    ],
)
def test_validate_gps_event_accepts_boundary_values(
    field_name: str,
    value: object,
) -> None:
    payload = valid_payload()
    payload[field_name] = value

    event = validate_gps_event(payload)

    assert getattr(event, field_name) == value


@pytest.mark.parametrize(
    "field_name",
    [
        "source_system",
        "external_event_id",
        "event_type",
        "event_timestamp",
        "driver_code",
        "vehicle_code",
        "latitude",
        "longitude",
        "speed_kmh",
        "heading_degrees",
        "gps_accuracy_m",
        "battery_level_percent",
    ],
)
def test_validate_gps_event_rejects_missing_required_fields(field_name: str) -> None:
    payload = valid_payload()
    del payload[field_name]

    with pytest.raises(ValidationError):
        validate_gps_event(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "speed_kmh",
        "heading_degrees",
        "gps_accuracy_m",
        "battery_level_percent",
    ],
)
def test_validate_gps_event_rejects_none_for_required_numeric_fields(
    field_name: str,
) -> None:
    payload = valid_payload()
    payload[field_name] = None

    with pytest.raises(ValidationError):
        validate_gps_event(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "source_system",
        "external_event_id",
        "event_timestamp",
        "driver_code",
        "vehicle_code",
    ],
)
def test_validate_gps_event_rejects_none_for_required_string_and_timestamp_fields(
    field_name: str,
) -> None:
    payload = valid_payload()
    payload[field_name] = None

    with pytest.raises(ValidationError):
        validate_gps_event(payload)


def test_validate_gps_event_rejects_extra_fields() -> None:
    payload = valid_payload()
    payload["unexpected_field"] = "not allowed"

    with pytest.raises(ValidationError):
        validate_gps_event(payload)


def test_validate_gps_event_parses_timestamp() -> None:
    event = validate_gps_event(valid_payload())

    assert isinstance(event.event_timestamp, datetime)
    assert event.event_timestamp.year == 2026
    assert event.event_timestamp.month == 6
    assert event.event_timestamp.day == 24
    assert event.event_timestamp.utcoffset() is not None


@pytest.mark.parametrize(
    "timestamp",
    [
        "not-a-timestamp",
        "2026-99-99T99:99:99",
        "",
    ],
)
def test_validate_gps_event_rejects_invalid_timestamp_format(
    timestamp: str,
) -> None:
    payload = valid_payload()
    payload["event_timestamp"] = timestamp

    with pytest.raises(ValidationError):
        validate_gps_event(payload)