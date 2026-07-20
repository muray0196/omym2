"""
Summary: Validates a durable Operation lookup against its expected running kind.
Why: organize, add, and refresh each guard Plan creation behind their own running Operation kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.domain.models.operation import Operation, OperationStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from omym2.domain.models.operation import OperationKind, OperationLookup
    from omym2.shared.ids import OperationId


def running_operation(
    lookup: Callable[[OperationId], OperationLookup | None],
    operation_id: OperationId | None,
    kind: OperationKind,
    *,
    required_message: str,
) -> Operation | None:
    """Return the running Operation of `kind` guarding this request, or None.

    Raises RuntimeError(required_message) when `operation_id` was supplied but
    `lookup` does not retain a matching running Operation of `kind`.
    """
    if operation_id is None:
        return None
    retained = lookup(operation_id)
    if (
        not isinstance(retained, Operation)
        or retained.kind is not kind
        or retained.status is not OperationStatus.RUNNING
    ):
        raise RuntimeError(required_message)
    return retained
