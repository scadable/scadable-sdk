"""Memory estimation for compiled projects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MemoryEstimate:
    """Estimated memory usage for a compiled project."""

    runtime_kb: int
    devices_kb: int
    registers_kb: int
    controllers_kb: int
    total_kb: int
    ram_limit_kb: int  # 0 = no limit (linux)
    target: str

    @property
    def fits(self) -> bool:
        return self.ram_limit_kb == 0 or self.total_kb <= self.ram_limit_kb

    @property
    def usage_pct(self) -> float:
        if self.ram_limit_kb == 0:
            return 0.0
        return self.total_kb / self.ram_limit_kb * 100


_PLATFORM_ESTIMATES: dict[str, dict[str, int]] = {
    "linux": {
        "runtime": 48,
        "per_device": 4,
        "per_register": 1,
        "per_controller": 2,
        "ram_limit": 0,
    },
    "esp32": {
        "runtime": 32,
        "per_device": 4,
        "per_register": 1,
        "per_controller": 2,
        "ram_limit": 520,
    },
}


def estimate_memory(
    devices: list[dict],
    controllers: list[dict],
    target: str,
) -> MemoryEstimate:
    """Estimate RAM usage for the given target platform."""
    est = _PLATFORM_ESTIMATES.get(target, _PLATFORM_ESTIMATES["linux"])

    total_registers = sum(len(d.get("registers", [])) for d in devices)

    runtime_kb = est["runtime"]
    devices_kb = len(devices) * est["per_device"]
    registers_kb = total_registers * est["per_register"]
    controllers_kb = len(controllers) * est["per_controller"]
    total_kb = runtime_kb + devices_kb + registers_kb + controllers_kb

    return MemoryEstimate(
        runtime_kb=runtime_kb,
        devices_kb=devices_kb,
        registers_kb=registers_kb,
        controllers_kb=controllers_kb,
        total_kb=total_kb,
        ram_limit_kb=est["ram_limit"],
        target=target,
    )
