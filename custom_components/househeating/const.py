"""Integration constants."""
DOMAIN = "househeating"
DEFAULT_NAME = "HouseHeating"
MINIMUM_HA = "2026.10.1"
DEFAULT_OPTIONS = {
    "scan_interval": 30,
    "slow_interval": 120,
    "measurement_divisor": 10,
    "setpoint_divisor": 10,
    "max_read": 16,
    "spacing_ms": 120,
    "timeout": 5,
    "extended": True,
    "curves": True,
    "max_heating": 60,
    "max_floor": 45,
    "max_dhw": 65,
    "allow_control": False,
    "authorized_identity": [],
}
