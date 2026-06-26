"""
One-shot pandas reporting for processed GPS records.

This module is intentionally separate from message ingestion.

It is responsible for:
- reading already-processed GPS records from Oracle
- joining GPS rows to driver and vehicle reference data
- summarising records with pandas
- writing a CSV report

It does not publish messages, consume messages, validate inbound payloads,
transform events, or insert GPS records.
"""

from __future__ import annotations

import os
from pathlib import Path

import oracledb
import pandas as pd

DEFAULT_REPORT_PATH = Path("reports/gps_summary.csv")

RAW_COLUMNS = [
    "source_system",
    "driver_code",
    "vehicle_code",
    "speed_kmh",
    "gps_accuracy_m",
    "battery_level_percent",
]

SUMMARY_COLUMNS = [
    "source_system",
    "driver_code",
    "vehicle_code",
    "record_count",
    "avg_speed_kmh",
    "max_speed_kmh",
    "avg_gps_accuracy_m",
    "min_battery_level_percent",
]

GPS_REPORT_SQL = """
SELECT g.source_system,
       d.driver_code,
       v.vehicle_code,
       g.speed_kmh,
       g.gps_accuracy_m,
       g.battery_level_percent
FROM   gps g
JOIN   drivers  d ON d.driver_id  = g.driver_id
JOIN   vehicles v ON v.vehicle_id = g.vehicle_id
ORDER BY g.source_system, d.driver_code, v.vehicle_code
"""


def _required_env(name: str) -> str:
    value = os.environ.get(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")

    return value


def fetch_gps_rows(
    *,
    user: str | None = None,
    password: str | None = None,
    dsn: str | None = None,
) -> pd.DataFrame:
    """
    Fetch processed GPS rows from Oracle for reporting.

    Optional connection arguments are mainly useful for tests or manual calls.
    If omitted, the same environment variables used by the Oracle repository
    are used.
    """

    db_user = user if user is not None else _required_env("LOGISTICS_DB_USER")
    db_password = (
        password if password is not None else _required_env("LOGISTICS_DB_PASSWORD")
    )
    db_dsn = dsn if dsn is not None else _required_env("ORACLE_DSN")

    connection = oracledb.connect(user=db_user, password=db_password, dsn=db_dsn)

    try:
        with connection.cursor() as cursor:
            cursor.execute(GPS_REPORT_SQL)  # pyright: ignore[reportUnknownMemberType]
            rows: list[tuple[object, ...]] = (  # pyright: ignore[reportUnknownVariableType]
                cursor.fetchall()  # pyright: ignore[reportUnknownMemberType]
            )
    finally:
        connection.close()

    return pd.DataFrame(rows, columns=RAW_COLUMNS)


def summarise_gps_records(rows: pd.DataFrame) -> pd.DataFrame:
    """
    Summarise GPS records by source system, driver, and vehicle.

    Pandas aggregate functions skip null values by default, which is acceptable
    for this first report.
    """

    if rows.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    grouped = rows.groupby(
        ["source_system", "driver_code", "vehicle_code"],
        dropna=False,
    )

    summary = grouped.agg(
        record_count=("source_system", "size"),
        avg_speed_kmh=("speed_kmh", "mean"),
        max_speed_kmh=("speed_kmh", "max"),
        avg_gps_accuracy_m=("gps_accuracy_m", "mean"),
        min_battery_level_percent=("battery_level_percent", "min"),
    ).reset_index()

    return summary[SUMMARY_COLUMNS]


def write_report(summary: pd.DataFrame, output_path: Path) -> None:
    """Write the summary report to CSV."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_path, index=False)


def generate_report(output_path: Path = DEFAULT_REPORT_PATH) -> pd.DataFrame:
    """
    Generate the GPS summary report.

    Returns the summary DataFrame to make the function easy to test and useful
    from an interactive Python session.
    """

    rows = fetch_gps_rows()
    summary = summarise_gps_records(rows)
    write_report(summary, output_path)

    return summary


def main() -> None:
    generate_report(DEFAULT_REPORT_PATH)
    print(f"Report written to {DEFAULT_REPORT_PATH}")


if __name__ == "__main__":
    main()
