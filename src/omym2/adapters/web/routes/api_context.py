"""
Summary: Resolves Web route dependencies at request time.
Why: Lets production and schema-only apps register exactly the same router without I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from omym2.features.bootstrap.dto import BootstrapResult


@dataclass(frozen=True, slots=True)
class ApiRouteContext:
    """Concrete collaborators used by the M1 Bootstrap route."""

    csrf_token: str
    get_bootstrap: Callable[[], BootstrapResult]


def get_api_route_context(request: Request) -> ApiRouteContext:
    """Return the context installed by the production application factory."""
    app = cast("FastAPI", request.scope["app"])
    return cast("ApiRouteContext", app.state.api_route_context)


type ApiContext = Annotated[ApiRouteContext, Depends(get_api_route_context)]
