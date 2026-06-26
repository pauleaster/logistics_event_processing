# tests/integration/test_oracle_repository.py
"""
Integration tests for the Python-to-Oracle GPS repository path.

These tests require a running local Oracle container and the logistics schema,
seed data, and PL/SQL package to have already been applied.

Expected setup from the project root:

    source ./set_env_vars.sh
    docker start logistics-oracle

Run this test file with:

    pytest tests/integration/test_oracle_repository.py -m "integration and oracle" -v

The required environment variables are:

    LOGISTICS_DB_USER
    LOGISTICS_DB_PASSWORD
    ORACLE_DSN

This file intentionally does not start or manage Docker containers. The tests
treat Oracle as an external integration dependency and verify that the Python
application path can validate, transform, and insert a GPS crumb through the
Oracle repository and PL/SQL package.

The first test is test-first by design. It is expected to fail until these
application modules are implemented:

    app.validator
    app.transformer
    app.oracle_repository
"""

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import TypedDict, cast
from collections.abc import Generator, Callable
from uuid import uuid4

import oracledb
import pytest

from app.event_processor import ProcessingStatus, process_gps_payload
from app.oracle_repository import OracleGpsRepository
from app.transformer import GpsRecord, transform_gps_event
from app.validator import validate_gps_event

pytestmark = [pytest.mark.integration, pytest.mark.oracle]


class GpsEventDict(TypedDict):
    source_system: str
    external_event_id: str
    event_type: str
    event_timestamp: str
    driver_code: str
    vehicle_code: str
    latitude: float
    longitude: float
    speed_kmh: float
    heading_degrees: int
    gps_accuracy_m: float
    battery_level_percent: int


class InsertedGpsRow(TypedDict):
    source_system: str
    external_event_id: str
    event_timestamp: datetime
    driver_code: str
    vehicle_code: str
    latitude: Decimal | float
    longitude: Decimal | float
    speed_kmh: Decimal | float
    heading_degrees: Decimal | int
    gps_accuracy_m: Decimal | float
    battery_level_percent: Decimal | int


VALID_GPS_EVENT: GpsEventDict = {
    "source_system": "DRIVER_APP",
    "external_event_id": "gps-it-python-oracle-000001",
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


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"Required environment variable is not set: {name}")
    return value


def _make_external_event_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def _make_event(
    external_event_id: str,
    **overrides: object,
) -> dict[str, object]:
    payload = dict(VALID_GPS_EVENT)
    payload["external_event_id"] = external_event_id
    payload.update(overrides)
    return payload


def _delete_gps_event(
    connection: oracledb.Connection,
    *,
    source_system: object,
    external_event_id: object,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(  # pyright: ignore[reportUnknownMemberType]
            """
            DELETE FROM gps
            WHERE source_system = :source_system
              AND external_event_id = :external_event_id
            """,
            {
                "source_system": str(source_system),
                "external_event_id": str(external_event_id),
            },
        )
    connection.commit()


def _insert_event_via_repository(payload: dict[str, object]) -> None:
    event = validate_gps_event(payload)
    record = transform_gps_event(event)
    repository = OracleGpsRepository()
    repository.insert_gps_record(record)


def _assert_oracle_error_contains(
    exc: BaseException,
    *fragments: str,
) -> None:
    error_text = str(exc)

    for fragment in fragments:
        assert fragment in error_text


@pytest.fixture()
def oracle_connection() -> Generator[oracledb.Connection, None, None]:
    connection = oracledb.connect(
        user=_required_env("LOGISTICS_DB_USER"),
        password=_required_env("LOGISTICS_DB_PASSWORD"),
        dsn=_required_env("ORACLE_DSN"),
    )

    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def clean_test_gps_row(
    oracle_connection: oracledb.Connection,
) -> Generator[None, None, None]:
    external_event_id = VALID_GPS_EVENT["external_event_id"]

    delete_sql = """
            delete from gps
            where external_event_id = :external_event_id
            """

    binds: dict[str, str] = {
        "external_event_id": external_event_id,
    }
    with oracle_connection.cursor() as cursor:
        cursor.execute(delete_sql, binds)  # pyright: ignore[reportUnknownMemberType]

    oracle_connection.commit()

    yield

    with oracle_connection.cursor() as cursor:
        cursor.execute(delete_sql, binds)  # pyright: ignore[reportUnknownMemberType]

    oracle_connection.commit()


@pytest.fixture
def cleanup_gps_events(
    oracle_connection: oracledb.Connection,
) -> Generator[Callable[[dict[str, object]], None], None, None]:
    payloads: list[dict[str, object]] = []

    def register(payload: dict[str, object]) -> None:
        payloads.append(payload)
        _delete_gps_event(
            oracle_connection,
            source_system=payload["source_system"],
            external_event_id=payload["external_event_id"],
        )

    yield register

    for payload in payloads:
        _delete_gps_event(
            oracle_connection,
            source_system=payload["source_system"],
            external_event_id=payload["external_event_id"],
        )


def test_valid_gps_event_is_validated_transformed_and_inserted_into_oracle(
    oracle_connection: oracledb.Connection,
) -> None:
    """
    Given a valid GPS event
    When the Python path validates, transforms, and inserts it using the Oracle repository
    Then one row appears in the gps table
    And the row is linked to the correct driver_id and vehicle_id
    And the inserted values match the source event
    """

    validated_event = validate_gps_event(dict(VALID_GPS_EVENT))
    gps_crumb_record = transform_gps_event(validated_event)

    repository = OracleGpsRepository()
    repository.insert_gps_record(gps_crumb_record)

    inserted_row = _fetch_inserted_gps_row(
        oracle_connection,
        external_event_id=VALID_GPS_EVENT["external_event_id"],
    )

    assert inserted_row is not None

    assert inserted_row["driver_code"] == VALID_GPS_EVENT["driver_code"]
    assert inserted_row["vehicle_code"] == VALID_GPS_EVENT["vehicle_code"]

    assert inserted_row["source_system"] == VALID_GPS_EVENT["source_system"]
    assert inserted_row["external_event_id"] == VALID_GPS_EVENT["external_event_id"]

    assert _to_float(inserted_row["latitude"]) == pytest.approx(
        VALID_GPS_EVENT["latitude"]
    )
    assert _to_float(inserted_row["longitude"]) == pytest.approx(
        VALID_GPS_EVENT["longitude"]
    )
    assert _to_float(inserted_row["speed_kmh"]) == pytest.approx(
        VALID_GPS_EVENT["speed_kmh"]
    )
    assert int(inserted_row["heading_degrees"]) == VALID_GPS_EVENT["heading_degrees"]
    assert _to_float(inserted_row["gps_accuracy_m"]) == pytest.approx(
        VALID_GPS_EVENT["gps_accuracy_m"]
    )
    assert (
        int(inserted_row["battery_level_percent"])
        == VALID_GPS_EVENT["battery_level_percent"]
    )
    expected_event_timestamp = (
        datetime.fromisoformat(VALID_GPS_EVENT["event_timestamp"])
        .astimezone(UTC)
        .replace(tzinfo=None)
    )
    assert inserted_row["event_timestamp"] == expected_event_timestamp


def _fetch_inserted_gps_row(
    connection: oracledb.Connection, external_event_id: str
) -> InsertedGpsRow | None:

    select_sql = """
            select
                g.source_system,
                g.external_event_id,
                g.event_timestamp,
                d.driver_code,
                v.vehicle_code,
                g.latitude,
                g.longitude,
                g.speed_kmh,
                g.heading_degrees,
                g.gps_accuracy_m,
                g.battery_level_percent
            from gps g
            join drivers d
                on d.driver_id = g.driver_id
            join vehicles v
                on v.vehicle_id = g.vehicle_id
            where g.external_event_id = :external_event_id
        """
    binds: dict[str, str] = {
        "external_event_id": external_event_id,
    }
    with connection.cursor() as cursor:
        cursor.execute(select_sql, binds)  # pyright: ignore[reportUnknownMemberType]

        row = cursor.fetchone()

        if row is None:
            return None
        description = cursor.description
        assert description is not None
        columns = [column.name.lower() for column in description]
        return cast(InsertedGpsRow, dict(zip(columns, row, strict=True)))


def _to_float(value: float | Decimal | int) -> float:
    return float(value)


def test_duplicate_gps_event_is_rejected_by_real_oracle_path(
    cleanup_gps_events: Callable[[dict[str, object]], None],
) -> None:
    payload = _make_event(_make_external_event_id("gps-duplicate"))
    cleanup_gps_events(payload)

    _insert_event_via_repository(payload)

    with pytest.raises(oracledb.Error) as exc_info:
        _insert_event_via_repository(payload)

    _assert_oracle_error_contains(
        exc_info.value,
        "ORA-20005",
        "Duplicate GPS event for source_system/external_event_id",
    )


def test_unknown_driver_code_is_rejected_by_plsql_package(
    cleanup_gps_events: Callable[[dict[str, object]], None],
) -> None:
    payload = _make_event(
        _make_external_event_id("gps-unknown-driver"),
        driver_code="DRV-UNKNOWN",
    )
    cleanup_gps_events(payload)

    with pytest.raises(oracledb.Error) as exc_info:
        _insert_event_via_repository(payload)

    _assert_oracle_error_contains(
        exc_info.value,
        "ORA-20001",
        "Active driver not found for driver_code",
    )


def test_unknown_vehicle_code_is_rejected_by_plsql_package(
    cleanup_gps_events: Callable[[dict[str, object]], None],
) -> None:
    payload = _make_event(
        _make_external_event_id("gps-unknown-vehicle"),
        vehicle_code="VH-UNKNOWN",
    )
    cleanup_gps_events(payload)

    with pytest.raises(oracledb.Error) as exc_info:
        _insert_event_via_repository(payload)

    _assert_oracle_error_contains(
        exc_info.value,
        "ORA-20003",
        "Active vehicle not found for vehicle_code",
    )


def test_real_duplicate_oracle_error_is_classified_by_event_processor(
    cleanup_gps_events: Callable[[dict[str, object]], None],
) -> None:
    payload = _make_event(_make_external_event_id("gps-processor-duplicate"))
    cleanup_gps_events(payload)

    _insert_event_via_repository(payload)

    repository = OracleGpsRepository()
    result = process_gps_payload(payload, repository)

    assert result.success is False
    assert result.status == ProcessingStatus.FAILED_DATABASE
    assert result.error_type == "DUPLICATE_GPS_EVENT"
    assert result.should_ack is False


def test_real_inactive_driver_is_classified_as_unknown_driver_with_current_plsql_wording(
    cleanup_gps_events: Callable[[dict[str, object]], None],
) -> None:
    payload = _make_event(
        _make_external_event_id("gps-inactive-driver"),
        driver_code="DRV4112",
    )
    cleanup_gps_events(payload)

    repository = OracleGpsRepository()
    result = process_gps_payload(payload, repository)

    assert result.success is False
    assert result.status == ProcessingStatus.FAILED_DATABASE
    assert result.error_type == "UNKNOWN_DRIVER"
    assert result.should_ack is False
    assert result.error_message is not None
    assert "Active driver not found for driver_code: DRV4112" in result.error_message


def test_real_inactive_vehicle_is_classified_as_unknown_vehicle_with_current_plsql_wording(
    cleanup_gps_events: Callable[[dict[str, object]], None],
) -> None:
    payload = _make_event(
        _make_external_event_id("gps-inactive-vehicle"),
        vehicle_code="VH-7705",
    )
    cleanup_gps_events(payload)

    repository = OracleGpsRepository()
    result = process_gps_payload(payload, repository)

    assert result.success is False
    assert result.status == ProcessingStatus.FAILED_DATABASE
    assert result.error_type == "UNKNOWN_VEHICLE"
    assert result.should_ack is False
    assert result.error_message is not None
    assert "Active vehicle not found for vehicle_code: VH-7705" in result.error_message


def test_invalid_latitude_check_constraint_is_enforced_by_real_oracle(
    cleanup_gps_events: Callable[[dict[str, object]], None],
) -> None:
    external_event_id = _make_external_event_id("gps-invalid-latitude")
    payload = _make_event(external_event_id)
    cleanup_gps_events(payload)

    event = validate_gps_event(payload)
    valid_record = transform_gps_event(event)

    invalid_record = GpsRecord(
        source_system=valid_record.source_system,
        external_event_id=valid_record.external_event_id,
        event_timestamp=valid_record.event_timestamp,
        driver_code=valid_record.driver_code,
        vehicle_code=valid_record.vehicle_code,
        latitude=91.0,
        longitude=valid_record.longitude,
        speed_kmh=valid_record.speed_kmh,
        heading_degrees=valid_record.heading_degrees,
        gps_accuracy_m=valid_record.gps_accuracy_m,
        battery_level_percent=valid_record.battery_level_percent,
    )

    repository = OracleGpsRepository()

    with pytest.raises(oracledb.Error) as exc_info:
        repository.insert_gps_record(invalid_record)

    _assert_oracle_error_contains(
        exc_info.value,
        "ORA-02290",
        "CK_GPS_LATITUDE",
    )
