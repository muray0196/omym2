"""
Summary: Composes bounded application logging from persisted settings.
Why: Keeps diagnostics writable, consistently rotated, and free of configured sensitive values.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, override

from omym2.adapters.config.application_paths import ApplicationPaths
from omym2.config import DESKTOP_LOG_ENCODING, DESKTOP_LOG_FORMAT
from omym2.features.common_ports import ConfigStoreIoError, ConfigStoreValidationError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from omym2.domain.models.app_config import AppConfig, LoggingConfig
    from omym2.platform.runtime_context import RuntimeContext

REDACTED_LOG_VALUE = "[REDACTED]"


class RedactingFormatter(logging.Formatter):
    """Format one record and replace exact configured sensitive values."""

    sensitive_values: tuple[str, ...]

    def __init__(self, format_string: str, sensitive_values: Iterable[str]) -> None:
        logging.Formatter.__init__(self, format_string)
        self.sensitive_values = tuple(
            sorted(
                {value for value in sensitive_values if value != ""},
                key=len,
                reverse=True,
            )
        )

    @override
    def format(self, record: logging.LogRecord) -> str:
        """Redact both the rendered message and rendered exception text."""
        rendered = super().format(record)
        for value in self.sensitive_values:
            rendered = rendered.replace(value, REDACTED_LOG_VALUE)
        return rendered


def resolve_log_file(application_root: Path, default_log_file: Path, config: LoggingConfig) -> Path:
    """Resolve a validated relative destination beneath writable application storage."""
    if config.destination is None:
        return default_log_file
    return application_root.joinpath(*PurePosixPath(config.destination).parts)


def configure_application_logging(
    log_file: Path,
    config: LoggingConfig,
    *,
    sensitive_values: Iterable[str] = (),
) -> None:
    """Install one bounded rotating root handler using persisted operational controls."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_file,
        maxBytes=config.rotation_max_bytes,
        backupCount=config.retention_files,
        encoding=DESKTOP_LOG_ENCODING,
    )
    handler.setFormatter(RedactingFormatter(DESKTOP_LOG_FORMAT, sensitive_values))
    root_logger = logging.getLogger()
    root_logger.setLevel(config.level)
    for existing_handler in tuple(root_logger.handlers):
        existing_handler.close()
        root_logger.removeHandler(existing_handler)
    root_logger.addHandler(handler)


def configure_runtime_logging(runtime: RuntimeContext) -> Path | None:
    """Configure a CLI/Web runtime, preserving command diagnostics when config or logging is unavailable."""
    try:
        config = runtime.config_store.load()
        paths = ApplicationPaths(runtime.application_root)
        log_file = resolve_log_file(paths.app_root, paths.desktop_log_file, config.logging)
        configure_application_logging(
            log_file,
            config.logging,
            sensitive_values=sensitive_log_values(paths, config),
        )
    except ConfigStoreIoError, ConfigStoreValidationError, OSError:
        return None
    return log_file


def sensitive_log_values(paths: ApplicationPaths, config: AppConfig) -> tuple[str, ...]:
    """Collect exact configured path and identity values that diagnostics must not expose."""
    values = [
        str(paths.app_root),
        str(paths.config_file),
        str(paths.database_file),
        config.paths.library,
        config.paths.incoming,
        config.logging.destination,
        config.musicbrainz.contact,
    ]
    return tuple(value for value in values if value is not None and value != "")
