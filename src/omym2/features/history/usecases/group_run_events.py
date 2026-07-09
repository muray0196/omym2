"""
Summary: Implements FileEvent grouping by target directory.
Why: Lets Run detail browsing summarize recorded file events without loading every event.
"""

from __future__ import annotations

from dataclasses import dataclass
from posixpath import dirname
from typing import TYPE_CHECKING

from omym2.features.history.usecases.get_run_header import RUN_NOT_FOUND_MESSAGE, RunNotFoundError
from omym2.shared.pagination import GroupCount, paginate_group_counts

if TYPE_CHECKING:
    from omym2.features.history.dto import GroupRunEventsRequest
    from omym2.features.history.ports import HistoryPorts
    from omym2.shared.pagination import Page

FILE_EVENT_GROUP_ROOT_LABEL = "(root)"  # target-directory group label for a Library-root target path


@dataclass(frozen=True, slots=True)
class GroupRunEventsUseCase:
    """List a Run's FileEvents grouped by target directory, ordered count DESC then key ASC.

    Deriving a target path's parent directory is a business rule, so it is
    computed here instead of in SQL.
    """

    ports: HistoryPorts

    def execute(self, request: GroupRunEventsRequest) -> Page[GroupCount]:
        """Return one page of target-directory groups for the Run.

        Raises RunNotFoundError for an unknown Run ID before listing paths.
        """
        with self.ports.uow as uow:
            if uow.runs.get(request.run_id) is None:
                raise RunNotFoundError(RUN_NOT_FOUND_MESSAGE)
            target_paths = uow.file_events.list_target_paths(request.run_id)

        counts: dict[str, int] = {}
        for target_path in target_paths:
            directory = dirname(target_path) or FILE_EVENT_GROUP_ROOT_LABEL
            counts[directory] = counts.get(directory, 0) + 1

        groups = tuple(GroupCount(key=directory, label=directory, count=count) for directory, count in counts.items())
        return paginate_group_counts(groups, request.page)
