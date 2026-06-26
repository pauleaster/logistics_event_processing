from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from unittest.mock import patch

import oracledb
from pytest import LogCaptureFixture

from app.event_processor import ProcessingStatus, process_gps_payload
from app.transformer import GpsRecord


@dataclass(slots=True)
class SuccessfulRepository:
    inserted_record: GpsRecord | None = None

    def insert_gps_record(self, record: GpsRecord) -> None:
        self.inserted_record = record


@dataclass(frozen=True, slots=True)
class FailingDatabaseRepository:
    message: str

    def insert_gps_record(self, record: GpsRecord) -> None:
        raise oracledb.DatabaseError(self.message)


def _valid_payload() -> dict[str, object]:
    return {
        "event_type": "GPS_CRUMB",
        "source_system": "DRIVER_APP",
        "external_event_id": "evt-001",
        "event_timestamp": datetime(2026, 6, 26, 5, 30, tzinfo=UTC),
        "driver_code": "DRV001",
        "vehicle_code": "VEH001",
        "latitude": -38.123456,
        "longitude": 145.123456,
        "speed_kmh": 82.5,
        "heading_degrees": 180,
        "gps_accuracy_m": 4.5,
        "battery_level_percent": 87,
    }


def test_process_gps_payload_inserts_valid_payload() -> None:
    repository = SuccessfulRepository()

    result = process_gps_payload(_valid_payload(), repository)

    assert result.success is True
    assert result.status == ProcessingStatus.INSERTED
    assert result.external_event_id == "evt-001"
    assert result.event_hash is not None
    assert result.error_type is None
    assert result.error_message is None
    assert result.should_ack is True
    assert repository.inserted_record is not None
    assert repository.inserted_record.external_event_id == "evt-001"


def test_process_gps_payload_rejects_invalid_payload() -> None:
    payload = _valid_payload()
    payload["latitude"] = 999.0

    repository = SuccessfulRepository()

    result = process_gps_payload(payload, repository)

    assert result.success is False
    assert result.status == ProcessingStatus.REJECTED_INVALID_PAYLOAD
    assert result.external_event_id == "evt-001"
    assert result.event_hash is not None
    assert result.error_type == "VALIDATION_ERROR"
    assert result.error_message is not None
    assert result.should_ack is True
    assert repository.inserted_record is None


def test_process_gps_payload_handles_duplicate_database_error() -> None:
    repository = FailingDatabaseRepository(
        message="ORA-00001: unique constraint violated"
    )

    result = process_gps_payload(_valid_payload(), repository)

    assert result.success is False
    assert result.status == ProcessingStatus.FAILED_DATABASE
    assert result.external_event_id == "evt-001"
    assert result.event_hash is not None
    assert result.error_type == "DUPLICATE_GPS_EVENT"
    assert result.error_message is not None
    assert result.should_ack is False


def test_process_gps_payload_handles_unknown_driver_database_error() -> None:
    repository = FailingDatabaseRepository(
        message="ORA-20001: unknown driver_code"
    )

    result = process_gps_payload(_valid_payload(), repository)

    assert result.success is False
    assert result.status == ProcessingStatus.FAILED_DATABASE
    assert result.external_event_id == "evt-001"
    assert result.event_hash is not None
    assert result.error_type == "UNKNOWN_DRIVER"
    assert result.error_message is not None
    assert result.should_ack is False


def test_process_gps_payload_handles_inactive_driver_database_error() -> None:
    repository = FailingDatabaseRepository(
        message="ORA-20002: driver is inactive"
    )

    result = process_gps_payload(_valid_payload(), repository)

    assert result.success is False
    assert result.status == ProcessingStatus.FAILED_DATABASE
    assert result.external_event_id == "evt-001"
    assert result.event_hash is not None
    assert result.error_type == "INACTIVE_DRIVER"
    assert result.error_message is not None
    assert result.should_ack is False


def test_process_gps_payload_handles_unknown_vehicle_database_error() -> None:
    repository = FailingDatabaseRepository(
        message="ORA-20003: unknown vehicle_code"
    )

    result = process_gps_payload(_valid_payload(), repository)

    assert result.success is False
    assert result.status == ProcessingStatus.FAILED_DATABASE
    assert result.external_event_id == "evt-001"
    assert result.event_hash is not None
    assert result.error_type == "UNKNOWN_VEHICLE"
    assert result.error_message is not None
    assert result.should_ack is False


def test_process_gps_payload_handles_inactive_vehicle_database_error() -> None:
    repository = FailingDatabaseRepository(
        message="ORA-20004: vehicle is inactive"
    )

    result = process_gps_payload(_valid_payload(), repository)

    assert result.success is False
    assert result.status == ProcessingStatus.FAILED_DATABASE
    assert result.external_event_id == "evt-001"
    assert result.event_hash is not None
    assert result.error_type == "INACTIVE_VEHICLE"
    assert result.error_message is not None
    assert result.should_ack is False


def test_process_gps_payload_database_error_logs_without_traceback(
    caplog: LogCaptureFixture,
) -> None:
    repository = FailingDatabaseRepository(
        message=(
            "ORA-20005: Duplicate GPS event for "
            "source_system/external_event_id: DRIVER_APP/gps-000001\n"
            'ORA-06512: at "LOGISTICS.EVENT_PROCESSING_PKG", line 91\n'
            "ORA-06512: at line 1"
        )
    )

    with caplog.at_level(logging.ERROR, logger="app.event_processor"):
        result = process_gps_payload(_valid_payload(), repository)

    assert result.success is False
    assert result.status == ProcessingStatus.FAILED_DATABASE
    assert result.error_type == "DUPLICATE_GPS_EVENT"
    assert result.error_message == (
        "ORA-20005: Duplicate GPS event for "
        "source_system/external_event_id: DRIVER_APP/gps-000001"
    )
    assert result.should_ack is False

    assert len(caplog.records) == 1
    record = caplog.records[0]

    assert record.message == "gps_event_database_failed"
    assert record.exc_info is None
    assert getattr(record, "source_system") == "DRIVER_APP"
    assert getattr(record, "external_event_id") == "evt-001"
    assert getattr(record, "event_hash") is not None
    assert getattr(record, "stage") == "oracle_insert"
    assert getattr(record, "status") == "failed"
    assert getattr(record, "error_type") == "DUPLICATE_GPS_EVENT"
    assert getattr(record, "error_message") == (
        "ORA-20005: Duplicate GPS event for "
        "source_system/external_event_id: DRIVER_APP/gps-000001"
    )


def test_process_gps_payload_transformation_failure_still_logs_traceback(
    caplog: LogCaptureFixture,
) -> None:
    repository = SuccessfulRepository()

    with patch(
        "app.event_processor.transform_gps_event",
        side_effect=RuntimeError("transform exploded"),
    ), caplog.at_level(logging.ERROR, logger="app.event_processor"):
        result = process_gps_payload(_valid_payload(), repository)

    assert result.success is False
    assert result.status == ProcessingStatus.FAILED_TRANSFORMATION
    assert result.error_type == "RuntimeError"
    assert result.error_message == "transform exploded"
    assert result.should_ack is False

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == "gps_event_transformation_failed"
    assert record.exc_info is not None