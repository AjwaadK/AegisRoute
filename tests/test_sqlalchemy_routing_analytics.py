from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from app.db.models import GenerationRequest
from app.repositories.sqlalchemy_routing_analytics import SQLAlchemyRoutingAnalyticsRepository


def test_time_filters_compile_to_bound_inclusive_and_exclusive_predicates() -> None:
    filters = SQLAlchemyRoutingAnalyticsRepository._time_filters(
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 2, 1, tzinfo=UTC),
    )
    compiled = str(
        GenerationRequest.__table__.select().where(*filters).compile(
            dialect=postgresql.dialect()
        )
    )
    assert "created_at >=" in compiled
    assert "created_at < " in compiled
    assert "2026-01-01" not in compiled
    assert "2026-02-01" not in compiled


def test_repository_contract_returns_analytics_data_not_orm_rows() -> None:
    assert SQLAlchemyRoutingAnalyticsRepository.get_routing_analytics.__annotations__["return"] == "RoutingAnalyticsData"
