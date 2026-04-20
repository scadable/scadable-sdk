# Scadable SDK

[![PyPI](https://img.shields.io/pypi/v/scadable-sdk.svg)](https://pypi.org/project/scadable-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/scadable-sdk.svg)](https://pypi.org/project/scadable-sdk/)
[![CI](https://github.com/scadable/scadable-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/scadable/scadable-sdk/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/scadable/scadable-sdk/branch/main/graph/badge.svg)](https://codecov.io/gh/scadable/scadable-sdk)
[![Tests](https://img.shields.io/badge/tests-172%20passing-brightgreen.svg)](https://github.com/scadable/scadable-sdk/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

**Write industrial device logic in Python. Compile to artifacts your
gateway runs. Version it like code.**

Scadable SDK is the authoring tool for the Scadable platform. You
declare which registers to read from your Modbus PLC, what controllers
should run on incoming data, and what to publish back to the cloud —
all in plain Python. The compiler turns your project into deployable
artifacts (YAML driver configs + manifest + bundle) that the
gateway-linux runtime reads on boot.

```bash
pip install scadable-sdk
```

## 30-second hello world

```bash
scadable init linux boiler-room
cd boiler-room
scadable add device modbus-tcp inlet-temp
scadable verify
scadable compile
ls build/   # → manifest.json, drivers/inlet-temp.yaml, bundle.tar.gz
```

The compile output goes straight onto a gateway:

```bash
scp build/drivers/inlet-temp.yaml \
    pi@gateway.local:/etc/scadable/devices/inlet-temp/config.yaml
ssh pi@gateway.local sudo systemctl restart scadable-gateway
```

The gateway picks it up, spawns the Modbus driver subprocess, and starts
publishing telemetry to your project.

## What you can write

```python
# devices/inlet_temp.py
from scadable import Device, Register, modbus_tcp, every, SECONDS

class InletTemp(Device):
    id = "inlet-temp"
    connection = modbus_tcp(host="${PLC_HOST}", port=502, slave=1)
    poll = every(5, SECONDS)
    registers = [
        Register(40001, "temperature",
                 dtype="float32", unit="°C", scale=0.1,
                 on_error="last_known"),
        Register(40003, "flow",
                 dtype="uint32", unit="L/min", endianness="little"),
    ]
```

```python
# controllers/safety.py
from scadable import Controller, Topics, on, SECONDS
from devices.inlet_temp import InletTemp

class Topics(Topics):
    OVERHEAT_ALERT = "alerts/inlet-overheat"

class SafetyMonitor(Controller):

    @on.interval(2, SECONDS)
    def check(self):
        t = InletTemp.temperature
        self.publish("inlet-data", {"temperature": t},
                     quality="good" if t < 200 else "stale")

        if t > 95:
            self.alert("critical", f"Inlet temp {t}°C — shutting down")
            InletTemp.flow = 0   # writes back to register
```

That's it. The DSL is declarative, target-agnostic, and reads like
English — your controls engineers can review it without learning
Python idioms.

## Why this exists

Industrial IoT projects today either:
- Hand-write driver code per device, in a per-vendor SDK that doesn't
  port between deployments, or
- Build flow-chart configurators in proprietary tools that lock you
  to one vendor and don't version-control cleanly.

Scadable's bet: device logic deserves the same treatment as application
code — written in a real language, reviewed in pull requests, tested
in CI, deployed via the same release pipeline as the rest of your
software. The SDK is the authoring half of that bet; the gateway is
the runtime half.

## Status

**v0.2.0** — current release.

| Target | Status        | Protocols                                         |
|--------|---------------|---------------------------------------------------|
| linux  | production    | modbus_tcp, modbus_rtu, ble, gpio, serial, i2c, rtsp |
| esp32  | preview       | DSL accepted; emitter ships in v0.3              |
| rtos   | preview       | DSL accepted; emitter ships in v0.4              |

Modbus (TCP + RTU) is the production protocol surface in v0.2.0;
other protocols compile but their gateway-side drivers are not yet
ready for production fleets.

## Documentation

- **[Getting started](docs/getting-started.md)** — full walkthrough
- **[DSL reference](docs/dsl-reference.md)** — every public symbol
- **[Targets](docs/targets.md)** — capability matrix per platform
- **[Migrating from v0.1](docs/migrating-from-v0.1.md)** — TOML→YAML, dtype, on_error
- **[Error catalog](docs/error-catalog.md)** — every compile error explained
- **[Architecture](docs/architecture.md)** — for contributors

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Quick path:

```bash
git clone https://github.com/scadable/scadable-sdk
cd scadable-sdk
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
pytest -q          # 172 tests, < 1 second
ruff check .
mypy --strict scadable
```

## License

Apache-2.0. See [LICENSE](LICENSE).
