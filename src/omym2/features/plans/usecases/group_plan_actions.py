"""
Summary: Implements Plan action grouping by target directory.
Why: Lets Web browsing show grouped Plan action counts by target directory with pagination.
"""

from __future__ import annotations

from dataclasses import dataclass
from posixpath import dirname
from typing import TYPE_CHECKING

from omym2.features.plans.usecases.get_plan_header import PLAN_NOT_FOUND_MESSAGE, PlanNotFoundError
from omym2.shared.pagination import GroupCount, paginate_group_counts

if TYPE_CHECKING:
    from omym2.features.plans.dto import GroupPlanActionsRequest
    from omym2.features.plans.ports import PlanQueryPorts
    from omym2.shared.pagination import Page

PLAN_ACTION_GROUP_ROOT_LABEL = "(root)"  # target-directory group label for a Library-root target path


@dataclass(frozen=True, slots=True)
class GroupPlanActionsUseCase:
    """List a Plan's actions grouped by target directory, ordered count DESC then key ASC.

    Deriving a target path's parent directory is a business rule, so it is
    computed here instead of in SQL. Actions with no recorded target_path
    (e.g. skip actions) have no target directory and are skipped.
    """

    ports: PlanQueryPorts

    def execute(self, request: GroupPlanActionsRequest) -> Page[GroupCount]:
        """Return one page of target-directory groups for the Plan.

        Raises PlanNotFoundError for an unknown Plan ID before listing paths.
        """
        with self.ports.uow as uow:
            if uow.plans.get(request.plan_id) is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            target_paths = uow.plan_actions.list_target_paths(request.plan_id)

        counts: dict[str, int] = {}
        for target_path in target_paths:
            directory = dirname(target_path) or PLAN_ACTION_GROUP_ROOT_LABEL
            counts[directory] = counts.get(directory, 0) + 1

        groups = tuple(GroupCount(key=directory, label=directory, count=count) for directory, count in counts.items())
        return paginate_group_counts(groups, request.page)
