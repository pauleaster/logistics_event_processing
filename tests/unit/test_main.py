from collections.abc import Callable
from dataclasses import dataclass

import pytest

import app.main as main_module
from app.event_processor import ProcessingResult, ProcessingStatus
from app.rabbitmq_config import RabbitMqConfig


JsonObject = dict[str, object]
Handler = Callable[[JsonObject], ProcessingResult]


@dataclass
class CapturedConsumerCall:
    config: RabbitMqConfig | None = None
    handler: Handler | None = None


class FakeRepository:
    pass


def test_run_wires_rabbitmq_consumer_to_event_processor_and_oracle_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RabbitMqConfig(
        host="localhost",
        port=5672,
        username="logistics",
        password="logistics",
        queue_name="gps_events",
    )
    repository = FakeRepository()
    captured_call = CapturedConsumerCall()

    def fake_from_env() -> RabbitMqConfig:
        return config

    def fake_oracle_repository() -> FakeRepository:
        return repository

    def fake_consume_json_events(
        *,
        config: RabbitMqConfig,
        handler: Handler,
    ) -> None:
        captured_call.config = config
        captured_call.handler = handler

    monkeypatch.setattr(main_module.RabbitMqConfig, "from_env", fake_from_env)
    monkeypatch.setattr(main_module, "OracleGpsRepository", fake_oracle_repository)
    monkeypatch.setattr(main_module, "consume_json_events", fake_consume_json_events)

    main_module.run()

    assert captured_call.config is config
    assert captured_call.handler is not None


def test_handler_returns_processing_result_from_event_processor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RabbitMqConfig(
        host="localhost",
        port=5672,
        username="logistics",
        password="logistics",
        queue_name="gps_events",
    )
    repository = FakeRepository()
    captured_call = CapturedConsumerCall()

    payload: JsonObject = {
        "event_type": "GPS_CRUMB",
        "source_system": "DRIVER_APP",
        "external_event_id": "event-001",
    }

    expected_result = ProcessingResult(
        success=True,
        status=ProcessingStatus.INSERTED,
        event_hash="abc123",
        external_event_id="event-001",
    )

    received_payload: JsonObject | None = None
    received_repository: object | None = None

    def fake_from_env() -> RabbitMqConfig:
        return config

    def fake_oracle_repository() -> FakeRepository:
        return repository

    def fake_process_gps_payload(
        incoming_payload: JsonObject,
        incoming_repository: object,
    ) -> ProcessingResult:
        nonlocal received_payload
        nonlocal received_repository

        received_payload = incoming_payload
        received_repository = incoming_repository
        return expected_result

    def fake_consume_json_events(
        *,
        config: RabbitMqConfig,
        handler: Handler,
    ) -> None:
        captured_call.config = config
        captured_call.handler = handler

    monkeypatch.setattr(main_module.RabbitMqConfig, "from_env", fake_from_env)
    monkeypatch.setattr(main_module, "OracleGpsRepository", fake_oracle_repository)
    monkeypatch.setattr(main_module, "process_gps_payload", fake_process_gps_payload)
    monkeypatch.setattr(main_module, "consume_json_events", fake_consume_json_events)

    main_module.run()

    assert captured_call.handler is not None

    actual_result = captured_call.handler(payload)

    assert actual_result is expected_result
    assert received_payload is payload
    assert received_repository is repository