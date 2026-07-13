"""
Summary: Builds the no-I/O FastAPI schema application.
Why: Exports exactly the production API route and Pydantic model set deterministically.
"""

from __future__ import annotations

from fastapi import FastAPI

from omym2.adapters.web.routes.api import create_api_router
from omym2.config import WEB_APP_TITLE


def create_api_schema_app() -> FastAPI:
    """Create the complete API schema app without constructing runtime collaborators."""
    app = FastAPI(
        title=WEB_APP_TITLE,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(create_api_router())
    return app
