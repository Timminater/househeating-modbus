"""Local HouseHeating/SolarEast heat-pump protocol library."""
from .device import HeatPump
from .models import CommunicationError, DeviceConfig, HeatPumpError, Identity, Snapshot, VerificationError, WriteRejected
from .registers import BINARY_FLAGS, BY_KEY, MODE_OPTIONS, REGISTERS, SELECTS, SETPOINT_KEYS, OperatingMode

__version__ = "0.1.0"
__all__ = ["HeatPump", "DeviceConfig", "HeatPumpError", "CommunicationError", "Identity",
           "Snapshot", "VerificationError", "WriteRejected", "BINARY_FLAGS", "BY_KEY",
           "MODE_OPTIONS", "REGISTERS", "SELECTS", "SETPOINT_KEYS", "OperatingMode"]
