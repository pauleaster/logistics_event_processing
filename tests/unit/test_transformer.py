# tests/unit/test_transformer.py

from datetime import datetime, timedelta, timezone
from typing import Any, TypeAlias

from app.transformer import GpsRecord, transform_gps_event
from app.validator import validate_gps_event


GpsPayload: TypeAlias = dict[str, Any]


def valid_gps_payload() -> GpsPayload:
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


def test_transform_gps_event_returns_gps_record() -> None:
    payload = valid_gps_payload()

    event = validate_gps_event(payload)
    record = transform_gps_event(event)

    assert isinstance(record, GpsRecord)
    assert record.source_system == "DRIVER_APP"
    assert record.external_event_id == "gps-000001"
    assert record.driver_code == "DRV1027"
    assert record.vehicle_code == "VH-4412"
    assert record.latitude == -37.813628
    assert record.longitude == 144.963058
    assert record.speed_kmh == 42.5
    assert record.heading_degrees == 87
    assert record.gps_accuracy_m == 8.5
    assert record.battery_level_percent == 76


def test_transform_gps_event_preserves_datetime_object() -> None:
    payload = valid_gps_payload()

    event = validate_gps_event(payload)
    record = transform_gps_event(event)

    assert isinstance(record.event_timestamp, datetime)
    assert record.event_timestamp.utcoffset() == timedelta(hours=10)


def test_transform_gps_event_does_not_include_event_type_in_oracle_params() -> None:
    payload = valid_gps_payload()

    event = validate_gps_event(payload)
    record = transform_gps_event(event)

    oracle_params = record.to_oracle_params()

    assert "event_type" not in oracle_params
    assert "p_event_type" not in oracle_params


def test_gps_record_to_oracle_params_uses_plsql_parameter_names() -> None:
    timestamp = datetime(2026, 6, 24, 9, 15, 30, tzinfo=timezone(timedelta(hours=10)))

    record = GpsRecord(
        source_system="DRIVER_APP",
        external_event_id="gps-000001",
        event_timestamp=timestamp,
        driver_code="DRV1027",
        vehicle_code="VH-4412",
        latitude=-37.813628,
        longitude=144.963058,
        speed_kmh=42.5,
        heading_degrees=87,
        gps_accuracy_m=8.5,
        battery_level_percent=76,
    )

    assert record.to_oracle_params() == {
        "p_source_system": "DRIVER_APP",
        "p_external_event_id": "gps-000001",
        "p_event_timestamp": timestamp,
        "p_driver_code": "DRV1027",
        "p_vehicle_code": "VH-4412",
        "p_latitude": -37.813628,
        "p_longitude": 144.963058,
        "p_speed_kmh": 42.5,
        "p_heading_degrees": 87,
        "p_gps_accuracy_m": 8.5,
        "p_battery_level_percent": 76,
    }