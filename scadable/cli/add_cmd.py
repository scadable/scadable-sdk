"""scadable add — scaffold devices, controllers, and models."""

from pathlib import Path

import typer
from rich import print as rprint

DEVICE_TEMPLATES = {
    "modbus-tcp": '''"""TODO: describe this device."""
from scadable import Device, Register, modbus_tcp, every, SECONDS, MINUTES


class {class_name}(Device):
    id = "{device_id}"
    name = "{display_name}"

    connection = modbus_tcp(host="${{SENSOR_HOST}}", port=502, slave=1)
    poll = every(5, SECONDS)
    historian = every(5, MINUTES)

    registers = [
        Register(40001, "value_1", unit="", scale=1),  # TODO: define registers
    ]
''',
    "modbus-rtu": '''"""TODO: describe this device."""
from scadable import Device, Register, modbus_rtu, every, SECONDS, MINUTES


class {class_name}(Device):
    id = "{device_id}"
    name = "{display_name}"

    connection = modbus_rtu(port="/dev/ttyUSB0", baudrate=9600, slave=1)
    poll = every(5, SECONDS)
    historian = every(5, MINUTES)

    registers = [
        Register(30001, "value_1", unit="", scale=1),  # TODO: define registers
    ]
''',
    "ble": '''"""TODO: describe this device."""
from scadable import Device, Characteristic, ble, every, SECONDS, MINUTES


class {class_name}(Device):
    id = "{device_id}"
    name = "{display_name}"

    connection = ble(mac="${{SENSOR_MAC}}")
    poll = every(30, SECONDS)
    historian = every(5, MINUTES)

    registers = [
        Characteristic("0x2A6E", "temperature", unit="°C", scale=0.01),  # TODO
    ]
''',
    "gpio": '''"""TODO: describe this device."""
from scadable import Device, Pin, gpio


class {class_name}(Device):
    id = "{device_id}"
    name = "{display_name}"

    connection = gpio()

    registers = [
        Pin(17, "input_1", mode="input_pullup", trigger="change"),  # TODO
    ]
''',
    "serial": '''"""TODO: describe this device."""
from scadable import Device, Field, serial, every, SECONDS


class {class_name}(Device):
    id = "{device_id}"
    name = "{display_name}"

    connection = serial(port="/dev/ttyUSB0", baudrate=9600)
    poll = every(10, SECONDS)

    registers = [
        Field(0, 2, "value_1", unit="", scale=1),  # TODO: define frame fields
    ]
''',
}

CONTROLLER_TEMPLATE = '''"""TODO: describe this controller."""
from scadable import Controller, on, SECONDS


class {class_name}(Controller):

    @on.interval(5, SECONDS)
    def run(self):
        pass  # TODO: implement logic
'''

MODEL_TEMPLATE = '''"""TODO: describe this model."""
from scadable import ONNXModel


class {class_name}(ONNXModel):
    id = "{model_id}"
    name = "{display_name}"
    version = "0.1.0"
    file = "models/{model_id}.onnx"  # TODO: add model file

    def preprocess(self, *args):
        """Transform raw sensor values into model input tensor."""
        return list(args)  # TODO: implement

    def inference(self, prediction):
        """Interpret model output into actionable result."""
        return {{"score": prediction[0]}}  # TODO: implement
'''


def _to_class_name(name: str) -> str:
    return "".join(word.capitalize() for word in name.replace("-", "_").split("_"))


def _to_snake(name: str) -> str:
    return name.replace("-", "_").lower()


def run_add(kind: str, protocol_or_name: str, name: str) -> None:
    if kind == "device":
        _add_device(protocol_or_name, name)
    elif kind == "controller":
        _add_controller(protocol_or_name)
    elif kind == "model":
        _add_model(protocol_or_name)
    else:
        rprint(f"[red]Unknown type '{kind}'. Use: device, controller, model[/red]")
        raise typer.Exit(1)


def _add_device(protocol: str, name: str) -> None:
    if protocol not in DEVICE_TEMPLATES:
        rprint(f"[red]Unknown protocol '{protocol}'. Options: {', '.join(DEVICE_TEMPLATES)}[/red]")
        raise typer.Exit(1)

    if not name:
        rprint("[red]Name required: scadable add device modbus-tcp my-sensor[/red]")
        raise typer.Exit(1)

    snake = _to_snake(name)
    class_name = _to_class_name(name)
    path = Path("devices") / f"{snake}.py"

    if path.exists():
        rprint(f"[red]{path} already exists.[/red]")
        raise typer.Exit(1)

    path.parent.mkdir(parents=True, exist_ok=True)
    content = DEVICE_TEMPLATES[protocol].format(
        class_name=class_name,
        device_id=name,
        display_name=name.replace("-", " ").title(),
    )
    path.write_text(content)
    rprint(f"[green]Created {path}[/green]")


def _add_controller(name: str) -> None:
    snake = _to_snake(name)
    class_name = _to_class_name(name)
    path = Path("controllers") / f"{snake}.py"

    if path.exists():
        rprint(f"[red]{path} already exists.[/red]")
        raise typer.Exit(1)

    path.parent.mkdir(parents=True, exist_ok=True)
    content = CONTROLLER_TEMPLATE.format(class_name=class_name)
    path.write_text(content)
    rprint(f"[green]Created {path}[/green]")


def _add_model(name: str) -> None:
    snake = _to_snake(name)
    class_name = _to_class_name(name)
    path = Path("models") / f"{snake}.py"

    if path.exists():
        rprint(f"[red]{path} already exists.[/red]")
        raise typer.Exit(1)

    path.parent.mkdir(parents=True, exist_ok=True)
    content = MODEL_TEMPLATE.format(
        class_name=class_name,
        model_id=name,
        display_name=name.replace("-", " ").title(),
    )
    path.write_text(content)
    rprint(f"[green]Created {path}[/green]")
