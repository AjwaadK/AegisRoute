import importlib

import pytest
from alembic.config import Config
from sqlalchemy import CheckConstraint, Text

from app.db.base import Base
from app.db.models import GenerationEvent, GenerationRequest


def column(model, name):
    return model.__table__.columns[name]


def check_constraint_names(model):
    return {constraint.name for constraint in model.__table__.constraints if isinstance(constraint, CheckConstraint)}


def test_session_module_imports_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    session_module = importlib.import_module("app.db.session")

    assert hasattr(session_module, "get_database_url")


def test_get_database_url_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    session_module = importlib.import_module("app.db.session")

    with pytest.raises(RuntimeError, match="DATABASE_URL environment variable is required"):
        session_module.get_database_url()


def test_get_database_url_returns_environment_value(monkeypatch):
    database_url = "postgresql+psycopg://user:password@localhost:5432/aegisroute_test"
    monkeypatch.setenv("DATABASE_URL", database_url)
    session_module = importlib.import_module("app.db.session")
    session_module = importlib.reload(session_module)

    assert session_module.get_database_url() == database_url


def test_session_loads_database_url_from_project_env(monkeypatch, tmp_path):
    database_url = "postgresql+psycopg://user:password@localhost:5432/aegisroute_test"
    (tmp_path / ".env").write_text(
        f"DATABASE_URL={database_url}\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("app.config.PROJECT_ROOT", tmp_path)
    session_module = importlib.import_module("app.db.session")
    session_module = importlib.reload(session_module)

    assert session_module.get_database_url() == database_url


def test_generation_table_names():
    assert GenerationRequest.__tablename__ == "generation_requests"
    assert GenerationEvent.__tablename__ == "generation_events"


def test_request_id_is_required_unique_and_not_separately_indexed():
    request_id = column(GenerationRequest, "request_id")

    assert request_id.nullable is False
    assert request_id.unique is True
    assert request_id.index is None


def test_important_string_columns_have_intentional_lengths():
    assert column(GenerationRequest, "request_id").type.length == 64
    assert column(GenerationRequest, "requested_model").type.length == 255
    assert column(GenerationRequest, "selected_model").type.length == 255
    assert column(GenerationRequest, "provider").type.length == 100
    assert isinstance(column(GenerationRequest, "routing_reason").type, Text)
    assert column(GenerationRequest, "status").type.length == 30
    assert column(GenerationRequest, "prompt_hash").type.length == 64
    assert column(GenerationRequest, "error_type").type.length == 100

    assert column(GenerationEvent, "event_type").type.length == 100
    assert column(GenerationEvent, "status").type.length == 30
    assert column(GenerationEvent, "provider").type.length == 100
    assert column(GenerationEvent, "model").type.length == 255
    assert column(GenerationEvent, "error_type").type.length == 100


def test_generation_request_required_and_nullable_columns():
    assert column(GenerationRequest, "requested_model").nullable is False
    assert column(GenerationRequest, "selected_model").nullable is True
    assert column(GenerationRequest, "provider").nullable is True
    assert column(GenerationRequest, "routing_reason").nullable is True
    assert column(GenerationRequest, "latency_ms").nullable is True
    assert column(GenerationRequest, "input_tokens").nullable is True
    assert column(GenerationRequest, "output_tokens").nullable is True


def test_generation_event_foreign_key_is_required_and_cascades():
    generation_request_id = column(GenerationEvent, "generation_request_id")
    foreign_key = next(iter(generation_request_id.foreign_keys))

    assert generation_request_id.nullable is False
    assert str(foreign_key.column) == "generation_requests.id"
    assert foreign_key.ondelete == "CASCADE"


def test_expected_check_constraints_exist():
    assert {
        "ck_generation_requests_message_count_gte_1",
        "ck_generation_requests_input_chars_gte_0",
        "ck_generation_requests_latency_ms_gte_0",
        "ck_generation_requests_input_tokens_gte_0",
        "ck_generation_requests_output_tokens_gte_0",
    }.issubset(check_constraint_names(GenerationRequest))
    assert "ck_generation_events_latency_ms_gte_0" in check_constraint_names(GenerationEvent)


def test_timestamp_columns_are_timezone_aware():
    for model, names in (
        (GenerationRequest, ("created_at", "updated_at")),
        (GenerationEvent, ("created_at",)),
    ):
        for name in names:
            assert column(model, name).type.timezone is True


def test_metadata_includes_generation_tables():
    assert {"generation_requests", "generation_events"}.issubset(Base.metadata.tables.keys())


def test_alembic_config_loads_script_location():
    config = Config("alembic.ini")

    assert config.get_main_option("script_location") == "alembic"


def test_initial_migration_does_not_create_redundant_request_id_index():
    migration = "alembic/versions/20260715_0001_create_generation_schema.py"

    with open(migration, encoding="utf-8") as migration_file:
        assert "ix_generation_requests_request_id" not in migration_file.read()


def test_routing_metadata_migration_follows_current_schema_head():
    migration = "alembic/versions/20260729_0002_add_routing_metadata.py"

    with open(migration, encoding="utf-8") as migration_file:
        contents = migration_file.read()

    assert 'revision: str = "20260729_0002"' in contents
    assert 'down_revision: Union[str, None] = "20260715_0001"' in contents
    assert 'new_column_name="requested_model"' in contents
    assert '"selected_model"' in contents
    assert '"routing_reason"' in contents
