from __future__ import annotations

import hashlib
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.producer import Producer
from app.rabbitmq_config import RabbitMqConfig


DEFAULT_SOURCE_SYSTEM = "DRIVER_APP"
DEFAULT_DRIVER_CODE = "DRV1027"
DEFAULT_VEHICLE_CODE = "VH-4412"
DEFAULT_INTERVAL_SECONDS = 1.0


def make_gps_event_id(
    *,
    source_system: str,
    driver_code: str,
    vehicle_code: str,
    event_timestamp: str,
) -> str:
    canonical = "|".join(
        [
            source_system,
            driver_code,
            vehicle_code,
            event_timestamp,
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_event(*, sequence: int) -> dict[str, object]:
    source_system = DEFAULT_SOURCE_SYSTEM
    driver_code = DEFAULT_DRIVER_CODE
    vehicle_code = DEFAULT_VEHICLE_CODE

    event_timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )

    # Start near Melbourne and vary slightly on each event.
    latitude = -37.8136 + (sequence * 0.0005)
    longitude = 144.9631 + (sequence * 0.0007)

    external_event_id = make_gps_event_id(
        source_system=source_system,
        driver_code=driver_code,
        vehicle_code=vehicle_code,
        event_timestamp=event_timestamp,
    )

    return {
        "external_event_id": external_event_id,
        "source_system": source_system,
        "event_type": "GPS_CRUMB",
        "driver_code": driver_code,
        "vehicle_code": vehicle_code,
        "event_timestamp": event_timestamp,
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "speed_kmh": 48.0,
        "heading_degrees": (sequence * 15) % 360,
        "gps_accuracy_m": 4.5,
        "battery_level_percent": 92,
    }


def main() -> None:
    config = RabbitMqConfig.from_env()
    producer = Producer(config)

    sequence = 0

    print("Publishing synthetic GPS events. Press Ctrl+C to stop.")

    try:
        while True:
            event = build_event(sequence=sequence)
            producer.publish_events(event)
            print(f"Published event: {event['external_event_id']}")
            sequence += 1
            time.sleep(DEFAULT_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("Stopped publishing synthetic GPS events.")


if __name__ == "__main__":
    main()
