"""PostgreSQL upgrade/downgrade coverage for routing metadata."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL is required for PostgreSQL migration tests",
)


def test_routing_metadata_upgrade_preserves_data_and_downgrades() -> None:
    assert DATABASE_URL is not None
    config = Config("alembic.ini")
    engine = create_engine(DATABASE_URL)

    try:
        command.downgrade(config, "base")
        command.upgrade(config, "20260715_0001")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO generation_requests (
                        request_id, model, provider, status, prompt_hash,
                        message_count, input_chars
                    ) VALUES (
                        'migration-request', 'public-model', 'mock', 'started',
                        :prompt_hash, 1, 5
                    )
                    """
                ),
                {"prompt_hash": "a" * 64},
            )

        command.upgrade(config, "head")
        columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("generation_requests")
        }
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT requested_model, selected_model, provider,
                           routing_reason
                    FROM generation_requests
                    WHERE request_id = 'migration-request'
                    """
                )
            ).one()

        assert row.requested_model == "public-model"
        assert row.selected_model is None
        assert row.provider == "mock"
        assert row.routing_reason is None
        assert columns["requested_model"]["nullable"] is False
        assert columns["selected_model"]["nullable"] is True
        assert columns["provider"]["nullable"] is True
        assert columns["routing_reason"]["nullable"] is True

        command.downgrade(config, "20260715_0001")
        downgraded_columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("generation_requests")
        }
        with engine.connect() as connection:
            preserved_model = connection.scalar(
                text(
                    "SELECT model FROM generation_requests "
                    "WHERE request_id = 'migration-request'"
                )
            )

        assert preserved_model == "public-model"
        assert "requested_model" not in downgraded_columns
        assert "selected_model" not in downgraded_columns
        assert "routing_reason" not in downgraded_columns
        assert downgraded_columns["provider"]["nullable"] is False
    finally:
        command.upgrade(config, "head")
        engine.dispose()
