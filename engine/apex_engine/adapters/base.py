"""Adapter interface: one subclass per sim.

The contract is deliberately tiny — an adapter only has to say whether the
game is up, and hand back normalized frames. Everything else (recording,
lap detection, analysis, UI) is sim-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..schema import TelemetryFrame, SessionContext


class BaseAdapter(ABC):
    """Translates one sim's raw telemetry into normalized frames."""

    #: short id used in CLI / logs, e.g. "lmu", "iracing", "sim"
    name: str = "base"
    #: human-readable game title
    game_title: str = "Unknown"
    #: target polling rate in Hz
    rate_hz: float = 50.0

    @abstractmethod
    def connect(self) -> bool:
        """Attach to the sim's data source. Return True on success.

        Called repeatedly until it succeeds, so it must be cheap to fail.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Release any handles."""

    @abstractmethod
    def is_active(self) -> bool:
        """True while the sim is running and producing data."""

    @abstractmethod
    def poll(self) -> Optional[TelemetryFrame]:
        """Return the latest frame, or None if no new data."""

    @abstractmethod
    def session(self) -> SessionContext:
        """Current session info (track, car, lengths)."""
