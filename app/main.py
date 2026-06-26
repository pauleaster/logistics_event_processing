"""
Application composition root.

This module wires together:
- RabbitMQ configuration
- RabbitMQ JSON consumer
- GPS event processor
- Oracle GPS repository

Business processing remains in app.event_processor.
Transport behaviour remains in app.consumer.
Oracle persistence remains in app.oracle_repository.
"""

from app.consumer import consume_json_events
from app.event_processor import ProcessingResult, process_gps_payload
from app.oracle_repository import OracleGpsRepository
from app.rabbitmq_config import RabbitMqConfig


def run() -> None:
    """
    Run the RabbitMQ -> GPS processing -> Oracle persistence pipeline.
    """
    config = RabbitMqConfig.from_env()
    repository = OracleGpsRepository()

    def handle_payload(payload: dict[str, object]) -> ProcessingResult:
        return process_gps_payload(payload, repository)

    consume_json_events(config=config, handler=handle_payload)


def main() -> None:
    """
    CLI entry point for `python -m app.main`.
    """
    run()


if __name__ == "__main__":
    main()