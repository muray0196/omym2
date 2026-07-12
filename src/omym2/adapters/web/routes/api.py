"""
Summary: Registers the renewed Web JSON API route set.
Why: Keeps production and schema-only applications on one exact typed router.
"""

from __future__ import annotations

from fastapi import APIRouter

from omym2.adapters.web.routes.bootstrap import create_bootstrap_router


def create_api_router() -> APIRouter:
    """Create the M1 Bootstrap-only API router without application I/O."""
    router = APIRouter()
    router.include_router(create_bootstrap_router())
    return router
