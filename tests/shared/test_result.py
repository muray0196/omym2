"""
Summary: Tests the Result primitive.
Why: Gives usecases an explicit success/failure return shape.
"""

from __future__ import annotations

from omym2.shared.result import Err, Ok, err, ok

SUCCESS_VALUE = "created"
FAILURE_VALUE = "blocked"


def test_ok_creates_success_branch() -> None:
    """ok stores the success value."""
    result = ok(SUCCESS_VALUE)

    assert isinstance(result, Ok)
    assert result.value == SUCCESS_VALUE


def test_err_creates_failure_branch() -> None:
    """err stores the failure value."""
    result = err(FAILURE_VALUE)

    assert isinstance(result, Err)
    assert result.error == FAILURE_VALUE
