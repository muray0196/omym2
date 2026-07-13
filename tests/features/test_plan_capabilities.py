"""
Summary: Tests backend-authoritative Plan capability projection.
Why: Prevents Web controls from inferring operation availability from status alone.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.features.plans.ports import PlanQueryPorts
from omym2.features.plans.usecases.get_plan_capabilities import (
    GetPlanCapabilitiesRequest,
    GetPlanCapabilitiesUseCase,
    PlanCapability,
    PlanCapabilityReason,
)
from omym2.features.plans.usecases.get_plan_header import PlanNotFoundError
from omym2.shared.ids import LibraryId, PlanId
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345670"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345671"))


def test_ready_plan_with_current_library_enables_apply_cancel_and_recreate() -> None:
    """A ready ordinary Plan exposes every M2 advisory capability."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library("/music"))
    uow.plans.save(_plan(PlanStatus.READY, PlanType.ADD))

    result = GetPlanCapabilitiesUseCase(PlanQueryPorts(uow)).execute(GetPlanCapabilitiesRequest(PLAN_ID))

    assert result.can_apply is True
    assert result.can_cancel is True
    assert result.can_recreate is True
    assert result.disabled_reasons == ()


def test_changed_library_root_disables_apply_without_disabling_cancel_or_recreate() -> None:
    """Apply reflects its recorded-root precondition while DB-only controls remain available."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library("/moved-music"))
    uow.plans.save(_plan(PlanStatus.READY, PlanType.REFRESH))

    result = GetPlanCapabilitiesUseCase(PlanQueryPorts(uow)).execute(GetPlanCapabilitiesRequest(PLAN_ID))

    assert result.can_apply is False
    assert result.can_cancel is True
    assert result.can_recreate is True
    assert [(item.capability, item.reason) for item in result.disabled_reasons] == [
        (PlanCapability.APPLY, PlanCapabilityReason.LIBRARY_ROOT_CHANGED)
    ]


def test_terminal_undo_plan_redirects_recreation_to_history() -> None:
    """Undo recreation remains Run-owned and terminal Plans stay single-use."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library("/music"))
    uow.plans.save(_plan(PlanStatus.APPLIED, PlanType.UNDO))

    result = GetPlanCapabilitiesUseCase(PlanQueryPorts(uow)).execute(GetPlanCapabilitiesRequest(PLAN_ID))

    assert result.can_apply is False
    assert result.can_cancel is False
    assert result.can_recreate is False
    assert [(item.capability, item.reason) for item in result.disabled_reasons] == [
        (PlanCapability.APPLY, PlanCapabilityReason.PLAN_NOT_READY),
        (PlanCapability.CANCEL, PlanCapabilityReason.PLAN_NOT_READY),
        (PlanCapability.RECREATE, PlanCapabilityReason.UNDO_RECREATES_FROM_HISTORY),
    ]


def test_unknown_plan_has_no_capability_snapshot() -> None:
    """An unknown stable identity remains a missing resource rather than an all-disabled Plan."""
    usecase = GetPlanCapabilitiesUseCase(PlanQueryPorts(InMemoryUnitOfWork()))

    with pytest.raises(PlanNotFoundError, match="Plan was not found"):
        _ = usecase.execute(GetPlanCapabilitiesRequest(PLAN_ID))


def _library(root_path: str) -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=root_path,
        path_policy_hash="policy",
        registered_at=NOW,
        status=LibraryStatus.REGISTERED,
        created_at=NOW,
        updated_at=NOW,
    )


def _plan(status: PlanStatus, plan_type: PlanType) -> Plan:
    return Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=plan_type,
        status=status,
        created_at=NOW,
        config_hash="config",
        library_root_at_plan="/music",
    )
