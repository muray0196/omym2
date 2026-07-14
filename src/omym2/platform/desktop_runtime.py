"""
Summary: Coordinates the desktop server and native window lifecycles.
Why: Guarantees graceful backend shutdown without moving business logic into the shell.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

LOGGER = logging.getLogger(__name__)


class DesktopServer(Protocol):
    """The local HTTP server behavior required by the desktop runtime."""

    def start(self) -> str:
        """Start the server and return its ready loopback URL."""
        ...

    def stop(self) -> None:
        """Request graceful shutdown and wait for accepted work to finish."""
        ...


class DesktopWindow(Protocol):
    """The native window behavior required by the desktop runtime."""

    def show(self, url: str) -> None:
        """Display the ready application URL until the final window closes."""
        ...


@dataclass(frozen=True, slots=True)
class DesktopRuntime:
    """Run one ready server behind one native window."""

    server: DesktopServer
    window: DesktopWindow

    def run(self) -> None:
        """Start the server before the window and always request safe shutdown."""
        try:
            url = self.server.start()
            LOGGER.info("Desktop server ready url=%s", url)
            self.window.show(url)
        except BaseException:
            try:
                self.server.stop()
            except Exception:
                LOGGER.exception("Desktop shutdown also failed while preserving the original error")
            raise
        else:
            self.server.stop()
