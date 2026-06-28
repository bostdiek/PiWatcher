"""PiSugar S battery monitor via I2C with development fallbacks."""

from typing import Protocol, cast

PISUGAR_I2C_ADDR = 0x57
PISUGAR_BATTERY_REG = 0x2A
PISUGAR_STATUS_REG = 0x55


class I2CBus(Protocol):
    """Minimal bus interface used by the PiSugar monitor."""

    def __enter__(self) -> "I2CBus": ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...

    def read_byte_data(self, address: int, register: int) -> int: ...


def _open_bus() -> I2CBus:
    try:
        from smbus2 import SMBus  # ty: ignore[unresolved-import]
    except ModuleNotFoundError:
        from smbus import SMBus  # ty: ignore[unresolved-import]

    return cast("I2CBus", SMBus(1))


def get_battery_level() -> int | None:
    """Read battery percentage from PiSugar S, or None when unavailable."""
    try:
        with _open_bus() as bus:
            value = int(bus.read_byte_data(PISUGAR_I2C_ADDR, PISUGAR_BATTERY_REG))
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None

    return max(0, min(100, value))


def is_charging() -> bool | None:
    """Return charging status, or None when the battery monitor is unavailable."""
    try:
        with _open_bus() as bus:
            status = int(bus.read_byte_data(PISUGAR_I2C_ADDR, PISUGAR_STATUS_REG))
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None

    return bool(status & 0x80)
