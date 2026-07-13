"""
Summary: Holds the native exclusive-operation lock in an independent process.
Why: Lets integration tests prove cross-process contention and crash release.
"""

from __future__ import annotations

import sys
from pathlib import Path

from omym2.adapters.fs.exclusive_operation_lock import FilesystemExclusiveOperationLock
from omym2.features.common_ports import ExclusiveOperationRequest

LOCK_HELD_MARKER = "lock-held"
LOCK_PATH_ARGUMENT_INDEX = 1
PROCESS_OPERATION_NAME = "independent_process_test"


def main() -> None:
    """Hold the requested lock until the parent closes or writes to stdin."""
    lock_file = Path(sys.argv[LOCK_PATH_ARGUMENT_INDEX])
    lock = FilesystemExclusiveOperationLock(lock_file)
    request = ExclusiveOperationRequest(operation_name=PROCESS_OPERATION_NAME)
    with lock.hold(request):
        _ = sys.stdout.write(f"{LOCK_HELD_MARKER}\n")
        _ = sys.stdout.flush()
        _ = sys.stdin.readline()


if __name__ == "__main__":
    main()
