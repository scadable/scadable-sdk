"""System-level commands available inside controllers."""

from __future__ import annotations


class _System:
    """System command namespace."""

    @staticmethod
    def shutdown(duration: int = 0, unit: str = "s") -> None:
        """Initiate gateway shutdown."""
        pass

    @staticmethod
    def reboot() -> None:
        """Reboot the gateway."""
        pass

    @staticmethod
    def info() -> dict:
        """Return gateway system info (uptime, memory, etc.)."""
        return {}


system = _System()
