"""PostgreSQL-backed read repository for routing analytics."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.analytics.contracts import (
    CountByName,
    ProviderAggregate,
    RouteAggregate,
    RoutingAnalyticsData,
)
from app.db.models import GenerationEvent, GenerationRequest


class SQLAlchemyRoutingAnalyticsRepository:
    """Execute a bounded set of six aggregation queries without loading rows."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    async def get_routing_analytics(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> RoutingAnalyticsData:
        filters = self._time_filters(start_time, end_time)
        completed = case((GenerationRequest.status == "completed", 1), else_=0)
        failed = case((GenerationRequest.status == "failed", 1), else_=0)
        routed = exists(
            select(GenerationEvent.id).where(
                GenerationEvent.generation_request_id == GenerationRequest.id,
                GenerationEvent.event_type == "generation_routed",
            )
        )

        with self._session_factory() as session:
            try:
                overall = session.execute(
                    select(
                        func.count(GenerationRequest.id),
                        func.coalesce(func.sum(completed), 0),
                        func.coalesce(func.sum(failed), 0),
                        func.avg(GenerationRequest.latency_ms),
                    ).where(*filters)
                ).one()
                providers = session.execute(
                    select(
                        GenerationRequest.provider,
                        func.count(GenerationRequest.id),
                        func.coalesce(func.sum(completed), 0),
                        func.coalesce(func.sum(failed), 0),
                        func.avg(GenerationRequest.latency_ms),
                    )
                    .where(*filters, GenerationRequest.provider.is_not(None))
                    .group_by(GenerationRequest.provider)
                    .order_by(GenerationRequest.provider)
                ).all()
                models = session.execute(
                    select(GenerationRequest.selected_model, func.count(GenerationRequest.id))
                    .where(*filters, GenerationRequest.selected_model.is_not(None))
                    .group_by(GenerationRequest.selected_model)
                    .order_by(GenerationRequest.selected_model)
                ).all()
                routes = session.execute(
                    select(
                        GenerationRequest.requested_model,
                        GenerationRequest.selected_model,
                        GenerationRequest.provider,
                        GenerationRequest.routing_reason,
                        func.count(GenerationRequest.id),
                    )
                    .where(
                        *filters,
                        GenerationRequest.selected_model.is_not(None),
                        GenerationRequest.provider.is_not(None),
                        GenerationRequest.routing_reason.is_not(None),
                    )
                    .group_by(
                        GenerationRequest.requested_model,
                        GenerationRequest.selected_model,
                        GenerationRequest.provider,
                        GenerationRequest.routing_reason,
                    )
                    .order_by(
                        GenerationRequest.requested_model,
                        GenerationRequest.selected_model,
                        GenerationRequest.provider,
                        GenerationRequest.routing_reason,
                    )
                ).all()
                errors = session.execute(
                    select(GenerationRequest.error_type, func.count(GenerationRequest.id))
                    .where(
                        *filters,
                        GenerationRequest.status == "failed",
                        GenerationRequest.error_type.is_not(None),
                    )
                    .group_by(GenerationRequest.error_type)
                    .order_by(GenerationRequest.error_type)
                ).all()
                stages = session.execute(
                    select(
                        func.coalesce(func.sum(case((~routed, 1), else_=0)), 0),
                        func.coalesce(func.sum(case((routed, 1), else_=0)), 0),
                    ).where(*filters, GenerationRequest.status == "failed")
                ).one()
            except Exception:
                session.rollback()
                raise

        return RoutingAnalyticsData(
            total_requests=int(overall[0]),
            successful_requests=int(overall[1]),
            failed_requests=int(overall[2]),
            average_latency_ms=float(overall[3]) if overall[3] is not None else None,
            requests_by_provider=tuple(CountByName(str(row[0]), int(row[1])) for row in providers),
            requests_by_selected_model=tuple(CountByName(str(row[0]), int(row[1])) for row in models),
            routing_distribution=tuple(
                RouteAggregate(str(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4]))
                for row in routes
            ),
            provider_metrics=tuple(
                ProviderAggregate(
                    str(row[0]), int(row[1]), int(row[2]), int(row[3]),
                    float(row[4]) if row[4] is not None else None,
                )
                for row in providers
            ),
            failures_by_error_type=tuple(CountByName(str(row[0]), int(row[1])) for row in errors),
            failures_before_routing=int(stages[0]),
            failures_after_routing=int(stages[1]),
        )

    @staticmethod
    def _time_filters(
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> tuple[object, ...]:
        filters: list[object] = []
        if start_time is not None:
            filters.append(GenerationRequest.created_at >= start_time)
        if end_time is not None:
            filters.append(GenerationRequest.created_at < end_time)
        return tuple(filters)
