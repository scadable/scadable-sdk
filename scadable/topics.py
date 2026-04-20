"""Project-level topic constants.

Customers drop a top-level `topics.py` in their project:

    from scadable import Topics

    class Topics(Topics):
        SENSOR_DATA  = "sensor-data"
        SETPOINT_CMD = "set_temperature"
        ALERT_HIGH   = "alert/high-temp"

Then everywhere they `self.publish(Topics.SENSOR_DATA, ...)` or
`@on.message(Topics.SETPOINT_CMD)`. The compiler validates that
every reference to a `Topics.X` resolves to a defined constant —
eliminates string-typo bugs across publishers + subscribers (which
were the #1 silent-failure mode in v0.1).

The base class itself does nothing at runtime — it's a marker so
the parser knows which subclass to walk.
"""

from __future__ import annotations


class Topics:
    """Base class for project-level topic constants.

    Subclass and define class-level string constants:

        class Topics(Topics):
            SENSOR_DATA = "sensor-data"

    The compiler reads the subclass at compile time and validates
    that every `Topics.X` reference in publishers + subscribers
    resolves to a defined constant.
    """

    pass
