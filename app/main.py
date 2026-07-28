from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.composition import ApplicationContainer, build_application_container


ContainerFactory = Callable[[], ApplicationContainer]


def create_app(container_factory: ContainerFactory = build_application_container) -> FastAPI:
    """Create the FastAPI application and its process-scoped lifecycle."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        container = container_factory()
        application.state.container = container
        try:
            yield
        finally:
            container.dispose()

    application = FastAPI(title="AI Compute Router", lifespan=lifespan)
    application.include_router(router)
    return application


app = create_app()
