"""
Summary: Registers the bundled Web JSON API route set.
Why: Keeps production and schema-only applications on one exact typed router.
"""

from __future__ import annotations

from fastapi import APIRouter

from omym2.adapters.web.routes.bootstrap import create_bootstrap_router
from omym2.adapters.web.routes.check import create_check_router
from omym2.adapters.web.routes.history import create_history_router
from omym2.adapters.web.routes.libraries import create_libraries_router
from omym2.adapters.web.routes.operations import create_operations_router
from omym2.adapters.web.routes.plans import create_plan_mutation_router, create_plans_router
from omym2.adapters.web.routes.settings import create_settings_router
from omym2.adapters.web.routes.tracks import create_tracks_router


def create_api_router() -> APIRouter:
    """Create the current typed API router without resolving application I/O."""
    router = APIRouter()
    router.include_router(create_bootstrap_router())
    router.include_router(create_settings_router())
    router.include_router(create_operations_router())
    router.include_router(create_libraries_router())
    router.include_router(create_plans_router())
    router.include_router(create_plan_mutation_router())
    router.include_router(create_tracks_router())
    router.include_router(create_check_router())
    router.include_router(create_history_router())
    return router
