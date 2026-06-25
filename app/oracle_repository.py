"""
Oracle repository for persisted GPS telemetry.

This module assumes validation and transformation have already happened.
It receives a database-ready GpsRecord and calls the Oracle PL/SQL package.
"""

import os
from collections.abc import Mapping
from typing import Any, cast

import oracledb

from app.transformer import GpsRecord


class OracleGpsRepository:
    """Repository for inserting transformed GPS records into Oracle."""

    def __init__(
        self,
        *,
        user: str | None = None,
        password: str | None = None,
        dsn: str | None = None,
    ) -> None:
        self.user = user or _required_env("LOGISTICS_DB_USER")
        self.password = password or _required_env("LOGISTICS_DB_PASSWORD")
        self.dsn = dsn or _required_env("ORACLE_DSN")

    def insert_gps_record(self, record: GpsRecord) -> None:
        """
        Insert one transformed GPS record via event_processing_pkg.insert_gps_crumb.

        The caller is responsible for validation and transformation before this method
        is called.

        On success, the transaction is committed.
        On database error, the transaction is rolled back and the exception propagates.
        """
        connection = oracledb.connect(
            user=self.user,
            password=self.password,
            dsn=self.dsn,
        )

        try:
            with connection.cursor() as cursor:
                cursor.callproc( # pyright: ignore[reportUnknownMemberType]
                    "event_processing_pkg.insert_gps_crumb",
                    [
                        _get_field(record, "source_system"),
                        _get_field(record, "external_event_id"),
                        _get_field(record, "event_timestamp"),
                        _get_field(record, "driver_code"),
                        _get_field(record, "vehicle_code"),
                        _get_field(record, "latitude"),
                        _get_field(record, "longitude"),
                        _get_field(record, "speed_kmh"),
                        _get_field(record, "heading_degrees"),
                        _get_field(record, "gps_accuracy_m"),
                        _get_field(record, "battery_level_percent"),
                    ],
                )

            connection.commit()

        except oracledb.Error:
            connection.rollback()
            raise

        finally:
            connection.close()


def insert_gps_record(record: GpsRecord) -> None:
    """
    Convenience function for inserting a transformed GPS record.

    This keeps simple call sites simple while still allowing OracleGpsRepository
    to be used directly where dependency injection is useful.
    """
    repository = OracleGpsRepository()
    repository.insert_gps_record(record)


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Required environment variable is not set: {name}")

    return value


def _get_field(record: GpsRecord, field_name: str) -> Any:
    """
    Read a field from a transformed GPS record.

    Supports dataclass/Pydantic-style attributes and dict-like records. This keeps
    the repository tolerant of the exact GpsRecord implementation without taking
    ownership of transformation.
    """
    if isinstance(record, Mapping):
        return cast(Any, record[field_name])

    return getattr(record, field_name)