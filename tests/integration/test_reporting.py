"""
Integration tests for the Oracle -> pandas reporting path.

These tests require a running local Oracle container and the logistics schema,
seed data, and PL/SQL package to have already been applied.

They deliberately test only the reporting read/query path. Message ingestion,
RabbitMQ, and the long-running consumer are not involved.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import oracledb
import pytest

from app.oracle_repository import OracleGpsRepository
from app.reporting import RAW_COLUMNS, fetch_gps_rows
from app.transformer import transform_gps_event
from app.validator import validate_gps_event


pytestmark = [
    pytest.mark.integration,
    pytest.mark.oracle,
]


def _required_env(name: str) -> str:
    value = os.environ.get(name)

    if not value:
        pytest.skip(f"Missing required environment variable: {name}")

    return value


def _connect() -> oracledb.Connection:
    return oracledb.connect(
        user=_required_env("LOGISTICS_DB_USER"),
        password=_required_env("LOGISTICS_DB_PASSWORD"),
        dsn=_required_env("ORACLE_DSN"),
    )


def _make_event(
    external_event_id: str,
    *,
    driver_code: str,
    vehicle_code: str,
    **overrides: object,
) -> dict[str, object]:
    event: dict[str, object] = {
        "event_type": "GPS_CRUMB",
        "source_system": "REPORTING_INTEGRATION_TEST",
        "external_event_id": external_event_id,
        "event_timestamp": datetime(2026, 1, 15, 10, 30, tzinfo=UTC).isoformat(),
        "driver_code": driver_code,
        "vehicle_code": vehicle_code,
        "latitude": -37.8136,
        "longitude": 144.9631,
        "speed_kmh": 72.5,
        "heading_degrees": 180,
        "gps_accuracy_m": 4.5,
        "battery_level_percent": 87,
    }
    event.update(overrides)

    return event


def _delete_gps_event(
    connection: oracledb.Connection,
    *,
    source_system: str,
    external_event_id: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute( # pyright: ignore[reportUnknownMemberType]
            """
            DELETE FROM gps
            WHERE source_system = :source_system
            AND   external_event_id = :external_event_id
            """,
            {
                "source_system": source_system,
                "external_event_id": external_event_id,
            },
        )

    connection.commit()


def _insert_event_via_repository(payload: dict[str, object]) -> None:
    validated_event = validate_gps_event(payload)
    gps_record = transform_gps_event(validated_event)

    repository = OracleGpsRepository(
        user=_required_env("LOGISTICS_DB_USER"),
        password=_required_env("LOGISTICS_DB_PASSWORD"),
        dsn=_required_env("ORACLE_DSN"),
    )

    repository.insert_gps_record(gps_record)


def _fetch_active_driver_code(connection: oracledb.Connection) -> str:
    with connection.cursor() as cursor:
        cursor.execute( # pyright: ignore[reportUnknownMemberType]
            """
            SELECT driver_code
            FROM   drivers
            WHERE  active_flag = 'Y'
            ORDER BY driver_code
            FETCH FIRST 1 ROW ONLY
            """
        )
        row = cursor.fetchone()

    if row is None:
        pytest.fail("No active driver found in seed data")

    return str(row[0])


def _fetch_active_vehicle_code(connection: oracledb.Connection) -> str:
    with connection.cursor() as cursor:
        cursor.execute( # pyright: ignore[reportUnknownMemberType]
            """
            SELECT vehicle_code
            FROM   vehicles
            WHERE  active_flag = 'Y'
            ORDER BY vehicle_code
            FETCH FIRST 1 ROW ONLY
            """
        )
        row = cursor.fetchone()

    if row is None:
        pytest.fail("No active vehicle found in seed data")

    return str(row[0])

def test_fetch_gps_rows_returns_dataframe_with_expected_columns() -> None:
    external_event_id = f"reporting-it-{uuid4()}"
    connection = _connect()

    driver_code = _fetch_active_driver_code(connection)
    vehicle_code = _fetch_active_vehicle_code(connection)

    payload = _make_event(
        external_event_id,
        driver_code=driver_code,
        vehicle_code=vehicle_code,
    )

    source_system = str(payload["source_system"])

    try:
        _delete_gps_event(
            connection,
            source_system=source_system,
            external_event_id=external_event_id,
        )

        _insert_event_via_repository(payload)

        rows = fetch_gps_rows()

        assert list(rows.columns) == RAW_COLUMNS

        matching_rows = rows[
            (rows["source_system"] == source_system)
            & (rows["driver_code"] == driver_code)
            & (rows["vehicle_code"] == vehicle_code)
        ]

        assert not matching_rows.empty

        inserted_row = matching_rows.iloc[0]

        assert inserted_row["speed_kmh"] == 72.5
        assert inserted_row["gps_accuracy_m"] == 4.5
        assert inserted_row["battery_level_percent"] == 87

    finally:
        _delete_gps_event(
            connection,
            source_system=source_system,
            external_event_id=external_event_id,
        )
        connection.close()
