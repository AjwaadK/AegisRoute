"""PostgreSQL upgrade/downgrade coverage for routing metadata."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema


DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL is required for PostgreSQL migration tests",
)


def test_routing_metadata_upgrade_preserves_data_and_downgrades() -> None:
    assert DATABASE_URL is not None
    config = Config("alembic.ini")
    schema_name = f"aegisroute_migration_{uuid4().hex}"
    admin_engine = create_engine(DATABASE_URL)
    database_url = make_url(DATABASE_URL)
    query = dict(database_url.query)
    query["options"] = f"-csearch_path={schema_name}"
    migration_url = database_url.set(query=query).render_as_string(
        hide_password=False
    )

    with admin_engine.begin() as connection:
        connection.execute(CreateSchema(schema_name))

    original_database_url = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = migration_url
    engine = create_engine(migration_url)

    try:
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
        engine.dispose()
        os.environ["DATABASE_URL"] = original_database_url
        with admin_engine.begin() as connection:
            connection.execute(DropSchema(schema_name, cascade=True))
        admin_engine.dispose()
