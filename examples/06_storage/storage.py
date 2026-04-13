"""Local storage configuration.

Three storage types for different purposes:
  data  — time-series ring buffer (oldest dropped when full)
  files — managed file storage (auto-cleanup by TTL then age)
  state — persistent key-value (survives reboots, never auto-deleted)

The compiler validates storage sizes against the target platform:
  Linux  → all sizes OK (disk-backed)
  ESP32  → max ~2MB data, ~1MB files (flash-backed)
  RTOS   → max ~64KB data, no files (flash KV only)
"""
from scadable.storage import data, files, state

# Sensor readings — circular buffer, oldest dropped when full
sensor_data = data("128MB")

# Photos and exports — auto-deleted after TTL
camera_roll = files("512MB", ttl="7d")

# Persistent state — calibration offsets, counters, config
device_config = state("1MB")
