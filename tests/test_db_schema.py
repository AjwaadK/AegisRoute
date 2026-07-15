from alembic.config import Config
from sqlalchemy import CheckConstraint

from app.db.base import Base
from app.db.models import GenerationEvent, GenerationRequest


def column(model, name):
    return model.__table__.columns[name]


def check_constraint_names(model):
    return {constraint.name for constraint in model.__table__.constraints if isinstance(constraint, CheckConstraint)}


def test_generation_table_names():
    assert GenerationRequest.__tablename__ == "generation_requests"
    assert GenerationEvent.__tablename__ == "generation_events"


def test_request_id_is_required_unique_and_indexed():
    request_id = column(GenerationRequest, "request_id")

    assert request_id.nullable is False
    assert request_id.unique is True
    assert request_id.index is True


def test_generation_request_required_and_nullable_columns():
    assert column(GenerationRequest, "provider").nullable is False
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
