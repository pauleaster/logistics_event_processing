"""
Processing boundary for one inbound GPS payload.

This module deliberately contains no RabbitMQ code. It processes one payload
through validation, transformation, and Oracle persistence, then returns a
typed result that later transport layers can use for ack/nack decisions.
"""

from dataclasses import dataclass
from enum import StrEnum
import logging
from collections.abc import Mapping
from typing import Protocol

import oracledb
from pydantic import ValidationError

from app.logging_config import make_event_hash
from app.transformer import GpsRecord, transform_gps_event
from app.validator import validate_gps_event


logger = logging.getLogger(__name__)


class GpsRepository(Protocol):
    def insert_gps_record(self, record: GpsRecord) -> None:
        ...


class ProcessingStatus(StrEnum):
    INSERTED = "inserted"
    REJECTED_INVALID_PAYLOAD = "rejected_invalid_payload"
    FAILED_TRANSFORMATION = "failed_transformation"
    FAILED_DATABASE = "failed_database"


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    success: bool
    status: ProcessingStatus
    event_hash: str | None
    external_event_id: str | None
    error_type: str | None = None
    error_message: str | None = None

    @property
    def should_ack(self) -> bool:
        """
        Transport-facing hint for future RabbitMQ handling.

        Invalid payloads should usually be acked because retrying the same
        malformed payload will not make it valid. Database failures may later
        be treated as nack/requeue depending on whether they are transient.
        """
        return self.status in {
            ProcessingStatus.INSERTED,
            ProcessingStatus.REJECTED_INVALID_PAYLOAD,
        }


def process_gps_payload(
    payload: Mapping[str, object],
    repository: GpsRepository,
) -> ProcessingResult:
    """
    Validate, transform, and persist one GPS payload.

    Invalid and failed events are logged but not persisted to Oracle.
    """

    event_hash = _safe_event_hash(payload)
    external_event_id = _extract_external_event_id(payload)

    try:
        validated_event = validate_gps_event(dict(payload))
    except ValidationError as exc:
        error_message = _summarise_validation_error(exc)

        logger.info(
            "gps_event_rejected",
            extra={
                "event_hash": event_hash,
                "external_event_id": external_event_id,
                "error_type": "VALIDATION_ERROR",
                "error_message": error_message,
            },
        )

        return ProcessingResult(
            success=False,
            status=ProcessingStatus.REJECTED_INVALID_PAYLOAD,
            event_hash=event_hash,
            external_event_id=external_event_id,
            error_type="VALIDATION_ERROR",
            error_message=error_message,
        )

    try:
        record = transform_gps_event(validated_event)
    except Exception as exc:
        # Transformation errors should be rare because validation should already
        # normalise the payload, but keep this boundary defensive.
        error_message = str(exc)

        logger.exception(
            "gps_event_transformation_failed",
            extra={
                "event_hash": event_hash,
                "external_event_id": external_event_id,
                "error_type": type(exc).__name__,
                "error_message": error_message,
            },
        )

        return ProcessingResult(
            success=False,
            status=ProcessingStatus.FAILED_TRANSFORMATION,
            event_hash=event_hash,
            external_event_id=external_event_id,
            error_type=type(exc).__name__,
            error_message=error_message,
        )

    try:
        repository.insert_gps_record(record)
    except oracledb.DatabaseError as exc:
        error_type = _classify_database_error(exc)
        error_message = _summarise_database_error(exc)

        logger.error(
            "gps_event_database_failed",
            extra={
                "event_hash": event_hash,
                "source_system": record.source_system,
                "external_event_id": record.external_event_id,
                "driver_code": record.driver_code,
                "vehicle_code": record.vehicle_code,
                "stage": "oracle_insert",
                "status": "failed",
                "error_type": error_type,
                "error_message": error_message,
            },
        )

        return ProcessingResult(
            success=False,
            status=ProcessingStatus.FAILED_DATABASE,
            event_hash=event_hash,
            external_event_id=record.external_event_id,
            error_type=error_type,
            error_message=error_message,
        )

    logger.info(
        "gps_event_inserted",
        extra={
            "event_hash": event_hash,
            "external_event_id": record.external_event_id,
            "driver_code": record.driver_code,
            "vehicle_code": record.vehicle_code,
        },
    )

    return ProcessingResult(
        success=True,
        status=ProcessingStatus.INSERTED,
        event_hash=event_hash,
        external_event_id=record.external_event_id,
    )


def _safe_event_hash(payload: Mapping[str, object]) -> str | None:
    try:
        return make_event_hash(payload)
    except Exception:
        logger.exception("gps_event_hash_failed")
        return None


def _extract_external_event_id(payload: Mapping[str, object]) -> str | None:
    value = payload.get("external_event_id")
    if isinstance(value, str) and value:
        return value
    return None


def _summarise_validation_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return str(exc)

    first_error = errors[0]
    location = ".".join(str(part) for part in first_error.get("loc", ()))
    message = str(first_error.get("msg", "validation failed"))

    if location:
        return f"{location}: {message}"

    return message


def _summarise_database_error(exc: oracledb.DatabaseError) -> str:
    return str(exc).splitlines()[0]


def _classify_database_error(exc: oracledb.DatabaseError) -> str:
    """
    Classify known Oracle/PLSQL failures without binding this layer too tightly
    to exact package internals.

    This catches both Oracle constraint errors and application errors raised
    from event_processing_pkg.
    """

    message = str(exc).upper()

    if "ORA-00001" in message or "DUPLICATE" in message:
        return "DUPLICATE_GPS_EVENT"

    if "DRIVER" in message and "INACTIVE" in message:
        return "INACTIVE_DRIVER"

    if "DRIVER" in message and (
        "UNKNOWN" in message
        or "NOT FOUND" in message
        or "INVALID" in message
    ):
        return "UNKNOWN_DRIVER"

    if "VEHICLE" in message and "INACTIVE" in message:
        return "INACTIVE_VEHICLE"

    if "VEHICLE" in message and (
        "UNKNOWN" in message
        or "NOT FOUND" in message
        or "INVALID" in message
    ):
        return "UNKNOWN_VEHICLE"

    return "DATABASE_ERROR"