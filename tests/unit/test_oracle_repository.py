from __future__ import annotations

from datetime import datetime
from typing import cast
from unittest.mock import MagicMock, patch

import oracledb
import pytest

from app.oracle_repository import OracleGpsRepository
from app.transformer import GpsRecord


def _sample_record() -> GpsRecord:
    return GpsRecord(
        source_system="TGE",
        external_event_id="evt-001",
        event_timestamp=datetime(2026, 6, 25, 0, 15, 30),
        driver_code="DRV001",
        vehicle_code="VEH001",
        latitude=-37.8136,
        longitude=144.9631,
        speed_kmh=42.5,
        heading_degrees=180,
        gps_accuracy_m=5.2,
        battery_level_percent=88,
    )


def _mock_connection_and_cursor() -> tuple[MagicMock, MagicMock]:
    connection = MagicMock(name="connection")
    cursor = MagicMock(name="cursor")
    cursor_context_manager = MagicMock(name="cursor_context_manager")

    cursor_context_manager.__enter__.return_value = cursor
    cursor_context_manager.__exit__.return_value = None
    connection.cursor.return_value = cursor_context_manager

    return connection, cursor


def test_constructor_uses_explicit_credentials() -> None:
    repository = OracleGpsRepository(
        user="explicit_user",
        password="explicit_password",
        dsn="localhost:1521/FREEPDB1",
    )

    assert repository.user == "explicit_user"
    assert repository.password == "explicit_password"
    assert repository.dsn == "localhost:1521/FREEPDB1"


def test_constructor_reads_credentials_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOGISTICS_DB_USER", "env_user")
    monkeypatch.setenv("LOGISTICS_DB_PASSWORD", "env_password")
    monkeypatch.setenv("ORACLE_DSN", "env_dsn")

    repository = OracleGpsRepository()

    assert repository.user == "env_user"
    assert repository.password == "env_password"
    assert repository.dsn == "env_dsn"


@pytest.mark.parametrize(
    "missing_env_var",
    [
        "LOGISTICS_DB_USER",
        "LOGISTICS_DB_PASSWORD",
        "ORACLE_DSN",
    ],
)
def test_constructor_raises_runtime_error_when_required_env_var_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    missing_env_var: str,
) -> None:
    monkeypatch.setenv("LOGISTICS_DB_USER", "env_user")
    monkeypatch.setenv("LOGISTICS_DB_PASSWORD", "env_password")
    monkeypatch.setenv("ORACLE_DSN", "env_dsn")
    monkeypatch.delenv(missing_env_var)

    with pytest.raises(RuntimeError):
        OracleGpsRepository()


def test_insert_gps_record_connects_with_configured_credentials() -> None:
    record = _sample_record()
    connection, _cursor = _mock_connection_and_cursor()

    with patch(
        "app.oracle_repository.oracledb.connect",
        return_value=connection,
    ) as connect_mock:
        repository = OracleGpsRepository(
            user="test_user",
            password="test_password",
            dsn="test_dsn",
        )

        repository.insert_gps_record(record)

    connect_mock.assert_called_once_with(
        user="test_user",
        password="test_password",
        dsn="test_dsn",
    )


def test_insert_gps_record_calls_plsql_package_with_record_params() -> None:
    record = _sample_record()
    connection, cursor = _mock_connection_and_cursor()

    with patch(
        "app.oracle_repository.oracledb.connect",
        return_value=connection,
    ):
        repository = OracleGpsRepository(
            user="test_user",
            password="test_password",
            dsn="test_dsn",
        )

        repository.insert_gps_record(record)

    cursor.callproc.assert_called_once_with(
        "event_processing_pkg.insert_gps_crumb",
        keyword_parameters=record.to_oracle_params(),
    )


def test_insert_gps_record_commits_on_success() -> None:
    record = _sample_record()
    connection, _cursor = _mock_connection_and_cursor()

    with patch(
        "app.oracle_repository.oracledb.connect",
        return_value=connection,
    ):
        repository = OracleGpsRepository(
            user="test_user",
            password="test_password",
            dsn="test_dsn",
        )

        repository.insert_gps_record(record)

    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()


def test_insert_gps_record_closes_connection_on_success() -> None:
    record = _sample_record()
    connection, _cursor = _mock_connection_and_cursor()

    with patch(
        "app.oracle_repository.oracledb.connect",
        return_value=connection,
    ):
        repository = OracleGpsRepository(
            user="test_user",
            password="test_password",
            dsn="test_dsn",
        )

        repository.insert_gps_record(record)

    connection.close.assert_called_once_with()


def test_insert_gps_record_rolls_back_and_reraises_on_database_error() -> None:
    record = _sample_record()
    connection, cursor = _mock_connection_and_cursor()
    database_error = oracledb.DatabaseError("insert failed")
    cursor.callproc.side_effect = database_error

    with patch(
        "app.oracle_repository.oracledb.connect",
        return_value=connection,
    ):
        repository = OracleGpsRepository(
            user="test_user",
            password="test_password",
            dsn="test_dsn",
        )

        with pytest.raises(oracledb.Error):
            repository.insert_gps_record(record)

    connection.rollback.assert_called_once_with()
    connection.commit.assert_not_called()


def test_insert_gps_record_closes_connection_on_database_error() -> None:
    record = _sample_record()
    connection, cursor = _mock_connection_and_cursor()
    cursor.callproc.side_effect = oracledb.DatabaseError("insert failed")

    with patch(
        "app.oracle_repository.oracledb.connect",
        return_value=connection,
    ):
        repository = OracleGpsRepository(
            user="test_user",
            password="test_password",
            dsn="test_dsn",
        )

        with pytest.raises(oracledb.Error):
            repository.insert_gps_record(record)

    connection.close.assert_called_once_with()


def test_module_level_insert_gps_record_delegates_to_repository() -> None:
    record = _sample_record()
    repository = MagicMock(spec=OracleGpsRepository)

    with patch(
        "app.oracle_repository.OracleGpsRepository",
        return_value=repository,
    ) as repository_class:
        from app.oracle_repository import insert_gps_record

        insert_gps_record(record)

    repository_class.assert_called_once_with()
    cast(MagicMock, repository.insert_gps_record).assert_called_once_with(record)