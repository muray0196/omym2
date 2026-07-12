"""
Summary: Defines the Web API Library projection.
Why: Exposes effective readiness without leaking SQLite representation names.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves timestamp schema types at runtime.
from uuid import UUID  # noqa: TC003  # Pydantic resolves UUID schema types at runtime.

from omym2.adapters.web.schemas.api_errors import ApiModel
from omym2.domain.models.library import LibraryStatus  # noqa: TC001  # Pydantic resolves enum schema types at runtime.


class LibraryResource(ApiModel):
    """One effective Library readiness resource."""

    library_id: UUID
    root_path: str
    status: LibraryStatus
    is_registered: bool
    registered_at: datetime | None
    path_policy_fingerprint: str
    is_path_policy_current: bool
