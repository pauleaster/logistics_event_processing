"""
Transformation logic for validated GPS events.

The validator is responsible for accepting or rejecting inbound payloads.
This module converts a validated GpsEvent into the clean persistence shape
expected by the Oracle repository layer.

Raw payloads and invalid events are intentionally not persisted here.
"""

from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any

from app.validator import GpsEvent


@dataclass(frozen=True, slots=True)
class GpsRecord:
    """
    Clean GPS record ready for Oracle persistence.

    This object deliberately excludes event_type because event_type is used
    only by the validation layer to confirm that the payload is a GPS_CRUMB.
    """

    source_system: str
    external_event_id: str
    event_timestamp: datetime
    driver_code: str
    vehicle_code: str
    latitude: float
    longitude: float
    speed_kmh: float
    heading_degrees: int
    gps_accuracy_m: float
    battery_level_percent: int

    def to_oracle_params(self) -> dict[str, Any]:
        """
        Return bind parameters using the PL/SQL procedure parameter names.

        The Oracle repository can pass this dictionary directly when calling:

            event_processing_pkg.insert_gps_crumb

        Prefer named binds over positional binds so that future procedure
        changes are easier to review.
        """
        return {
            "p_source_system": self.source_system,
            "p_external_event_id": self.external_event_id,
            "p_event_timestamp": self.event_timestamp,
            "p_driver_code": self.driver_code,
            "p_vehicle_code": self.vehicle_code,
            "p_latitude": self.latitude,
            "p_longitude": self.longitude,
            "p_speed_kmh": self.speed_kmh,
            "p_heading_degrees": self.heading_degrees,
            "p_gps_accuracy_m": self.gps_accuracy_m,
            "p_battery_level_percent": self.battery_level_percent,
        }


def transform_gps_event(event: GpsEvent) -> GpsRecord:
    """
    Transform a validated GpsEvent into a clean Oracle persistence record.

    The input must already have passed Pydantic validation. This function does
    not revalidate business rules; it only removes validation-only fields and
    prepares the persistence shape.

    Event timestamps are normalised to UTC and made timezone-naive because the
    Oracle GPS table stores event timestamps as plain TIMESTAMP values.
    """
    return GpsRecord(
        source_system=event.source_system,
        external_event_id=event.external_event_id,
        event_timestamp=event.event_timestamp.astimezone(UTC).replace(tzinfo=None),
        driver_code=event.driver_code,
        vehicle_code=event.vehicle_code,
        latitude=event.latitude,
        longitude=event.longitude,
        speed_kmh=event.speed_kmh,
        heading_degrees=event.heading_degrees,
        gps_accuracy_m=event.gps_accuracy_m,
        battery_level_percent=event.battery_level_percent,
    )
