"""
Summary: Defines apply feature request data.
Why: Gives apply usecases stable contracts before file mutation support exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.shared.ids import PlanId


@dataclass(frozen=True, slots=True)
class ApplyPlanRequest:
    """Request to apply one reviewed Plan."""

    plan_id: PlanId
