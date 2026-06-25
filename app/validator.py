# app/validator.py
"""
Validation for incoming GPS crumb events.

This module validates the external event shape only. It does not transform
the event into database/procedure fields; that belongs in app.transformer.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GpsEvent(BaseModel):
    """
    Validated GPS crumb event received from the external driver app stream.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    source_system: str
    external_event_id: str
    event_type: Literal["GPS_CRUMB"]
    event_timestamp: datetime

    driver_code: str = Field(min_length=1)
    vehicle_code: str = Field(min_length=1)

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    speed_kmh: float = Field(ge=0)
    heading_degrees: int = Field(ge=0, le=359)
    gps_accuracy_m: float = Field(ge=0)
    battery_level_percent: int = Field(ge=0, le=100)


def validate_gps_event(payload: dict[str, Any]) -> GpsEvent:
    """
    Validate a raw GPS event payload.

    Raises:
        pydantic.ValidationError: if the payload is invalid.

    Returns:
        GpsEvent: the validated event model.
    """
    return GpsEvent.model_validate(payload)