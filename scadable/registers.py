"""Register descriptors for device field definitions.

Each register type (Register, Characteristic, Pin, Field) acts as
a Python descriptor. When accessed on a Device class, it returns
the register metadata. When accessed on a Device instance (at
runtime on the gateway), it returns the current sensor value.

For IDE autocomplete: the __get__ return type is `float` so editors
treat `LineSensor.temperature` as a number. At import time, the
Device metaclass creates these descriptors from the registers list.
"""

from __future__ import annotations

# Modbus + similar register data types. The compiler emits this into
# the YAML so the gateway driver knows how many words to read and how
# to decode them. uint16 is the safe default — every Modbus register
# is at minimum 1 word (16 bits) wide.
DTYPES: tuple[str, ...] = (
    "uint16", "int16",
    "uint32", "int32",
    "float32", "float64",
    "bool",
)

# Read-failure policy. Drives the gateway driver's behavior when a
# register read errors (timeout, CRC fail, exception code).
#   skip       — drop this sample silently; the next tick tries again
#   last_known — emit the previous successful value tagged quality="stale"
#   fail       — propagate as an alert and skip the sample
ON_ERROR_POLICIES: tuple[str, ...] = ("skip", "last_known", "fail")


class Register:
    """Modbus register — address determines read/write capability.

    30000-39999 = input registers (read-only)
    40000-49999 = holding registers (read/write unless writable=False)
    00001-09999 = coils (read/write, boolean)
    10000-19999 = discrete inputs (read-only, boolean)

    `dtype` (default "uint16") tells the driver how many words to read
    and how to decode them. A 32-bit value (uint32, int32, float32)
    occupies 2 consecutive registers starting at `address`. Use
    `endianness` to pick byte order if your device isn't big-endian.

    `on_error` (default "skip") picks the read-failure policy:
        skip       — drop this sample, try again next tick
        last_known — emit the previous successful value as `quality="stale"`
        fail       — surface as an alert and skip the sample
    """

    def __init__(self, address: int, name: str, *,
                 unit: str = "", scale: float = 1.0,
                 writable: bool | None = None, store: bool = True,
                 dtype: str = "uint16",
                 endianness: str = "big",
                 on_error: str = "skip"):
        if dtype not in DTYPES:
            raise ValueError(
                f"Register {name!r}: dtype={dtype!r} is not one of "
                f"{', '.join(DTYPES)}"
            )
        if endianness not in ("big", "little"):
            raise ValueError(
                f"Register {name!r}: endianness={endianness!r} must be "
                f"'big' or 'little'"
            )
        if on_error not in ON_ERROR_POLICIES:
            raise ValueError(
                f"Register {name!r}: on_error={on_error!r} is not one of "
                f"{', '.join(ON_ERROR_POLICIES)}"
            )
        self.address = address
        self.name = name
        self.unit = unit
        self.scale = scale
        self.store = store
        self.dtype = dtype
        self.endianness = endianness
        self.on_error = on_error
        self._value: float = 0.0

        # Auto-detect writable from address range if not explicit
        if writable is not None:
            self.writable = writable
        elif 40000 <= address < 50000 or 1 <= address < 10000:
            self.writable = True
        else:
            self.writable = False

    def __set_name__(self, owner: type, attr_name: str) -> None:
        self._attr_name = attr_name

    def __get__(self, obj: object, objtype: type | None = None) -> float:
        if obj is None:
            return self  # type: ignore[return-value]
        return self._value

    def __set__(self, obj: object, value: float) -> None:
        if not self.writable:
            raise AttributeError(
                f"Register '{self.name}' (address {self.address}) is read-only"
            )
        self._value = value

    def __repr__(self) -> str:
        rw = "RW" if self.writable else "RO"
        return f"Register({self.address}, '{self.name}', {rw}, unit='{self.unit}')"


class Characteristic:
    """BLE GATT characteristic — identified by UUID string."""

    def __init__(self, uuid: str, name: str, *,
                 unit: str = "", scale: float = 1.0, store: bool = True):
        self.uuid = uuid
        self.name = name
        self.unit = unit
        self.scale = scale
        self.store = store
        self.writable = False
        self._value: float = 0.0

    def __set_name__(self, owner: type, attr_name: str) -> None:
        self._attr_name = attr_name

    def __get__(self, obj: object, objtype: type | None = None) -> float:
        if obj is None:
            return self  # type: ignore[return-value]
        return self._value

    def __repr__(self) -> str:
        return f"Characteristic('{self.uuid}', '{self.name}', unit='{self.unit}')"


class Pin:
    """GPIO pin definition."""

    def __init__(self, pin: int, name: str, *,
                 mode: str = "input", trigger: str | None = None,
                 unit: str = "", scale: float = 1.0, store: bool = True):
        self.pin = pin
        self.name = name
        self.mode = mode
        self.trigger = trigger
        self.unit = unit
        self.scale = scale
        self.store = store
        self.writable = mode == "output"
        self._value: float = 0.0

    def __set_name__(self, owner: type, attr_name: str) -> None:
        self._attr_name = attr_name

    def __get__(self, obj: object, objtype: type | None = None) -> float:
        if obj is None:
            return self  # type: ignore[return-value]
        return self._value

    def __set__(self, obj: object, value: float) -> None:
        if not self.writable:
            raise AttributeError(f"Pin {self.pin} '{self.name}' is not an output")
        self._value = value

    def __repr__(self) -> str:
        return f"Pin({self.pin}, '{self.name}', mode='{self.mode}')"


class Field:
    """Serial/custom protocol field — byte offset + length."""

    def __init__(self, offset: int, length: int, name: str = "", *,
                 unit: str = "", scale: float = 1.0, store: bool = True):
        self.offset = offset
        self.length = length
        self.name = name
        self.unit = unit
        self.scale = scale
        self.store = store
        self.writable = False
        self._value: float = 0.0

    def __set_name__(self, owner: type, attr_name: str) -> None:
        if not self.name:
            self.name = attr_name
        self._attr_name = attr_name

    def __get__(self, obj: object, objtype: type | None = None) -> float:
        if obj is None:
            return self  # type: ignore[return-value]
        return self._value

    def __repr__(self) -> str:
        return f"Field(offset={self.offset}, len={self.length}, '{self.name}')"
