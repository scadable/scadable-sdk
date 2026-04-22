"""Simulators for the Scadable pipeline.

Currently ships:

- ``scadable.sim.modbus_sim`` — a pymodbus-backed Modbus TCP server used by
  the e2e smoke test (``e2e-tests/tests/test_pipeline_smoke.py``) and by
  developers who want to drive the ``01_basic_sensor`` example without
  buying a real PLC.

Sims are an *optional* extra (``pip install scadable-sdk[sim]``) so the
pymodbus dependency doesn't follow normal SDK users into production.
"""

__all__: list[str] = []
