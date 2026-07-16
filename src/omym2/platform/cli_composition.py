"""
Summary: Builds the CLI CommandDependencies bundle from concrete adapters.
Why: Wires all 12 CLI commands' ports and factories through one shared RuntimeContext.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.add import AddCommandDependencies
from omym2.adapters.cli.commands.apply import ApplyCommandDependencies
from omym2.adapters.cli.commands.check import CheckCommandDependencies
from omym2.adapters.cli.commands.organize import OrganizeCommandDependencies
from omym2.adapters.cli.commands.refresh import RefreshCommandDependencies
from omym2.adapters.cli.commands.settings import SettingsCommandPorts
from omym2.adapters.cli.commands.undo import UndoCommandDependencies
from omym2.adapters.cli.main import CommandDependencies
from omym2.domain.models.operation import OperationKind
from omym2.features.add.usecases.create_add_plan import CreateAddPlanUseCase
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.usecases.apply_plan import ApplyPlanUseCase
from omym2.features.check.usecases.check_library import CheckLibraryUseCase
from omym2.features.organize.usecases.create_organize_plan import CreateOrganizePlanUseCase
from omym2.features.refresh.usecases.create_refresh_plan import CreateRefreshPlanUseCase
from omym2.features.undo.dto import CreateUndoPlanRequest
from omym2.features.undo.usecases.create_undo_plan import CreateUndoPlanUseCase
from omym2.platform.artist_ids_composition import artist_ids_command_ports_for
from omym2.platform.cli_path_normalization import normalize_cli_path
from omym2.platform.feature_composition import (
    build_apply_plan_ports,
    build_check_library_ports,
    build_create_add_plan_ports,
    build_create_organize_plan_ports,
    build_create_refresh_plan_ports,
    build_create_undo_plan_ports,
    build_history_ports,
    build_inspect_file_ports,
    build_plan_query_ports,
    build_settings_ports,
    build_uow,
)
from omym2.platform.operation_composition import OperationRuntime
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI

    from omym2.domain.models.plan import Plan
    from omym2.domain.models.run import Run
    from omym2.features.add.dto import CreateAddPlanRequest
    from omym2.features.check.dto import CheckLibraryRequest, CheckLibraryResult
    from omym2.features.organize.dto import CreateOrganizePlanRequest, OrganizeLibraryResult
    from omym2.features.refresh.dto import CreateRefreshPlanRequest
    from omym2.platform.runtime_context import RuntimeContext
    from omym2.shared.ids import PlanId, RunId


def _build_web_app(config_path: Path, database_path: Path) -> FastAPI:
    """Build the settings Web app without importing its stack for other commands."""
    from omym2.platform.web_composition import build_web_app  # noqa: PLC0415  # Intentional settings-only import.

    return build_web_app(config_path, database_path)


def build_command_dependencies(
    config_path: Path | None = None,
    database_path: Path | None = None,
) -> CommandDependencies:
    """Build the full per-command dependency bundle for one CLI invocation.

    Every eagerly built field runs on each invocation before command dispatch,
    so it must stay side-effect-free at construction (no I/O, no optional
    imports); anything heavier belongs behind one of the factory fields.
    """
    runtime = runtime_context_for(config_path, database_path)
    return command_dependencies_for_runtime(runtime)


def command_dependencies_for_runtime(runtime: RuntimeContext) -> CommandDependencies:
    """Build the command bundle over one already-resolved process runtime."""
    operations = OperationRuntime(runtime)
    return CommandDependencies(
        add=AddCommandDependencies(
            create_add_plan=lambda request: _create_add_plan(runtime, operations, request),
            apply_plan=lambda plan_id: _apply_plan(runtime, operations, plan_id),
            normalize_source_path=normalize_cli_path,
        ),
        apply=ApplyCommandDependencies(
            uow_factory=lambda: build_uow(runtime),
            apply_plan=lambda plan_id: _apply_plan(runtime, operations, plan_id),
        ),
        artist_ids=artist_ids_command_ports_for(runtime, operations),
        check=CheckCommandDependencies(check_library=lambda request: _check_library(runtime, operations, request)),
        config=build_settings_ports(runtime),
        history=build_history_ports(runtime),
        inspect=build_inspect_file_ports(runtime),
        organize=OrganizeCommandDependencies(
            create_organize_plan=lambda request: _create_organize_plan(runtime, operations, request),
            apply_plan=lambda plan_id: _apply_plan(runtime, operations, plan_id),
            normalize_library_root=normalize_cli_path,
        ),
        plans=build_plan_query_ports(runtime),
        refresh=RefreshCommandDependencies(
            create_refresh_plan=lambda request: _create_refresh_plan(runtime, operations, request),
            apply_plan=lambda plan_id: _apply_plan(runtime, operations, plan_id),
            normalize_target_path=normalize_cli_path,
        ),
        settings=SettingsCommandPorts(
            web_app_factory=lambda: _build_web_app(runtime.config_file, runtime.database_file)
        ),
        undo=UndoCommandDependencies(
            create_undo_plan=lambda run_id: _create_undo_plan(runtime, operations, run_id),
            apply_plan=lambda plan_id: _apply_plan(runtime, operations, plan_id),
        ),
    )


def _apply_plan(runtime: RuntimeContext, operations: OperationRuntime, plan_id: PlanId) -> Run:
    return operations.run_inline_apply(
        plan_id=plan_id,
        canonical_request={"plan_id": plan_id},
        work=lambda operation_id, run_id: ApplyPlanUseCase(build_apply_plan_ports(runtime)).execute(
            ApplyPlanRequest(
                plan_id=plan_id,
                options=ApplyOptions(yes=True),
                run_id=run_id,
                operation_id=operation_id,
            )
        ),
    )


def _create_undo_plan(runtime: RuntimeContext, operations: OperationRuntime, run_id: RunId) -> Plan:
    return operations.run_inline(
        kind=OperationKind.UNDO_PLAN,
        canonical_request={"run_id": run_id},
        run_id=run_id,
        work=lambda operation_id: CreateUndoPlanUseCase(build_create_undo_plan_ports(runtime)).execute(
            CreateUndoPlanRequest(run_id=run_id, operation_id=operation_id)
        ),
    )


def _create_add_plan(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: CreateAddPlanRequest,
) -> Plan:
    return operations.run_inline(
        kind=OperationKind.ADD_PLAN,
        canonical_request={"library_id": request.library_id, "source_path": request.source_path},
        library_id=request.library_id,
        work=lambda operation_id: CreateAddPlanUseCase(build_create_add_plan_ports(runtime)).execute(
            replace(request, operation_id=operation_id)
        ),
    )


def _create_organize_plan(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: CreateOrganizePlanRequest,
) -> OrganizeLibraryResult:
    return operations.run_inline(
        kind=OperationKind.ORGANIZE_PLAN,
        canonical_request={
            "library_root": request.library_root,
            "trust_stat": request.trust_stat,
        },
        work=lambda operation_id: CreateOrganizePlanUseCase(build_create_organize_plan_ports(runtime)).execute(
            replace(request, operation_id=operation_id)
        ),
    )


def _create_refresh_plan(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: CreateRefreshPlanRequest,
) -> Plan:
    return operations.run_inline(
        kind=OperationKind.REFRESH_PLAN,
        canonical_request={
            "include_all": request.include_all,
            "library_id": request.library_id,
            "target_kind": request.target_kind,
            "target_path": request.target_path,
            "track_id": request.track_id,
            "trust_stat": request.trust_stat,
        },
        library_id=request.library_id,
        work=lambda operation_id: CreateRefreshPlanUseCase(build_create_refresh_plan_ports(runtime)).execute(
            replace(request, operation_id=operation_id)
        ),
    )


def _check_library(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: CheckLibraryRequest,
) -> CheckLibraryResult:
    return operations.run_inline(
        kind=OperationKind.CHECK,
        canonical_request={"library_id": request.library_id, "trust_stat": request.trust_stat},
        library_id=request.library_id,
        work=lambda operation_id: CheckLibraryUseCase(build_check_library_ports(runtime)).execute(
            replace(request, operation_id=operation_id)
        ),
    )
