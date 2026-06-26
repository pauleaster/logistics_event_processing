from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app import reporting


def test_summarise_empty_dataframe_returns_expected_columns() -> None:
    rows = pd.DataFrame(columns=reporting.RAW_COLUMNS)

    summary = reporting.summarise_gps_records(rows)

    assert list(summary.columns) == reporting.SUMMARY_COLUMNS
    assert summary.empty


def test_summarise_groups_by_source_system_driver_code_vehicle_code() -> None:
    rows = pd.DataFrame(
        [
            {
                "source_system": "telematics",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "speed_kmh": 50.0,
                "gps_accuracy_m": 5.0,
                "battery_level_percent": 90,
            },
            {
                "source_system": "telematics",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "speed_kmh": 60.0,
                "gps_accuracy_m": 7.0,
                "battery_level_percent": 80,
            },
            {
                "source_system": "telematics",
                "driver_code": "DRV002",
                "vehicle_code": "VEH002",
                "speed_kmh": 70.0,
                "gps_accuracy_m": 9.0,
                "battery_level_percent": 75,
            },
        ]
    )

    summary = reporting.summarise_gps_records(rows)

    assert len(summary) == 2

    first_group = summary[
        (summary["source_system"] == "telematics")
        & (summary["driver_code"] == "DRV001")
        & (summary["vehicle_code"] == "VEH001")
    ].iloc[0]

    assert first_group["record_count"] == 2


def test_summarise_calculates_avg_and_max_speed() -> None:
    rows = pd.DataFrame(
        [
            {
                "source_system": "telematics",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "speed_kmh": 40.0,
                "gps_accuracy_m": 5.0,
                "battery_level_percent": 95,
            },
            {
                "source_system": "telematics",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "speed_kmh": 80.0,
                "gps_accuracy_m": 10.0,
                "battery_level_percent": 85,
            },
        ]
    )

    summary = reporting.summarise_gps_records(rows)

    result = summary.iloc[0]

    assert result["avg_speed_kmh"] == 60.0
    assert result["max_speed_kmh"] == 80.0


def test_summarise_calculates_min_battery_and_avg_accuracy() -> None:
    rows = pd.DataFrame(
        [
            {
                "source_system": "telematics",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "speed_kmh": 40.0,
                "gps_accuracy_m": 4.0,
                "battery_level_percent": 90,
            },
            {
                "source_system": "telematics",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "speed_kmh": 80.0,
                "gps_accuracy_m": 8.0,
                "battery_level_percent": 70,
            },
        ]
    )

    summary = reporting.summarise_gps_records(rows)

    result = summary.iloc[0]

    assert result["avg_gps_accuracy_m"] == 6.0
    assert result["min_battery_level_percent"] == 70


def test_summarise_handles_null_values_without_error() -> None:
    rows = pd.DataFrame(
        [
            {
                "source_system": "telematics",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "speed_kmh": 50.0,
                "gps_accuracy_m": None,
                "battery_level_percent": None,
            },
            {
                "source_system": "telematics",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "speed_kmh": None,
                "gps_accuracy_m": 10.0,
                "battery_level_percent": 80,
            },
        ]
    )

    summary = reporting.summarise_gps_records(rows)

    result = summary.iloc[0]

    assert result["record_count"] == 2
    assert result["avg_speed_kmh"] == 50.0
    assert result["avg_gps_accuracy_m"] == 10.0
    assert result["min_battery_level_percent"] == 80


def test_write_report_creates_parent_directory_and_writes_csv(tmp_path: Path) -> None:
    summary = pd.DataFrame(
        [
            {
                "source_system": "telematics",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "record_count": 1,
                "avg_speed_kmh": 50.0,
                "max_speed_kmh": 50.0,
                "avg_gps_accuracy_m": 5.0,
                "min_battery_level_percent": 90,
            }
        ]
    )
    output_path = tmp_path / "reports" / "gps_summary.csv"

    reporting.write_report(summary, output_path)

    assert output_path.exists()

    written = pd.read_csv(output_path)

    assert list(written.columns) == reporting.SUMMARY_COLUMNS
    assert written.iloc[0]["source_system"] == "telematics"
    assert written.iloc[0]["driver_code"] == "DRV001"
    assert written.iloc[0]["vehicle_code"] == "VEH001"


def test_generate_report_fetches_summarises_and_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = pd.DataFrame(
        [
            {
                "source_system": "telematics",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "speed_kmh": 50.0,
                "gps_accuracy_m": 5.0,
                "battery_level_percent": 90,
            },
            {
                "source_system": "telematics",
                "driver_code": "DRV001",
                "vehicle_code": "VEH001",
                "speed_kmh": 70.0,
                "gps_accuracy_m": 7.0,
                "battery_level_percent": 80,
            },
        ]
    )
    output_path = tmp_path / "gps_summary.csv"

    def fake_fetch_gps_rows() -> pd.DataFrame:
        return rows

    monkeypatch.setattr(reporting, "fetch_gps_rows", fake_fetch_gps_rows)

    summary = reporting.generate_report(output_path)

    assert output_path.exists()
    assert len(summary) == 1
    assert summary.iloc[0]["record_count"] == 2
    assert summary.iloc[0]["avg_speed_kmh"] == 60.0