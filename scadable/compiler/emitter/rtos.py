"""RTOS emitter — preview, ships in v0.4.

Reserved as a stub so the emitter registry has the right shape and
the validator can already check capability fits at compile time.
Implementation lands when the RTOS firmware runtime is ready to
consume the artifacts.
"""

from __future__ import annotations

from pathlib import Path

from ..._targets import TargetNotImplementedError
from .base import Emitter


class RtosEmitter(Emitter):
    """RTOS — DSL accepted, runtime in progress."""

    def emit_driver_configs(self, devices: list[dict], output_dir: Path) -> list[Path]:
        raise TargetNotImplementedError(
            "RTOS emitter is not implemented in v0.2.0 — scheduled for v0.4. "
            "The DSL accepts target='rtos' for forward-compat (validator will "
            "still flag protocol/dtype mismatches), but compile output is not "
            "yet emitted. Track the milestone at "
            "https://github.com/scadable/scadable-sdk/milestones."
        )
