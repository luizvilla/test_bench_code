"""
ThingSet drop-in for comm_protocol/src/Shield_Class.py (ticket #16).

`ThingSetShield.sendCommand(action, *args, delay=...)` keeps the signature the
supervisor already uses, and turns each action into one ThingSet write on the
bench firmware built from OwnTech Core `serial_thingset_example_modular`
(plus the bench objects `wPhaseShift_deg` and `wDeadTimeComp`). Every write is
read back, because the firmware silently restores out-of-range values and
still answers `:84 Changed`. Any error raises; nothing is only printed.

Port selection (`find_thingset_port`): the board enumerates two CDC-ACM ports
with the same VID/PID, `if00` (console + scope data) and `if02` (ThingSet
shell). We pick `if02` explicitly and never open anything at 1200 baud (that
baud rate on `if00` reboots the board into MCUboot).

SPDX-License-Identifier: LGPL-2.1
"""

import glob
import math
import os
import re
import time

# OwnTech USB IDs of the ThingSet bench firmware: Zephyr defaults
# (CONFIG_USB_DEVICE_VID/PID), product string "SPIN". The string-protocol
# firmware used PID 0x0101 ("COMM-MASTER", from the comm_protocol lib.conf).
THINGSET_USB_VID = 0x2FE3
THINGSET_USB_PID = 0x0100
THINGSET_INTERFACE = 2           # if02 = ThingSet shell, if00 = console
SAFE_BAUDRATE = 115200
BOOTLOADER_BAUDRATE = 1200       # never used: reboots the board into MCUboot
BY_ID_DIR = "/dev/serial/by-id"

# Config/Mode enum of the firmware: IDLE, POWER_ON, POWER_OFF
MODES = {"IDLE": 0, "POWER_ON": 1, "POWER_OFF": 2}

# Bench limits that the string-protocol firmware enforced and the ThingSet
# callbacks do not (research §2 / §6): checked here before anything is sent.
DEAD_TIME_MIN_NS = 100
DEAD_TIME_MAX_NS = 2000
PHASE_MIN_DEG = 0.0
PHASE_MAX_DEG = 360.0

# Readback tolerance for floats: the firmware serialises floats with a fixed
# number of decimals (wDutyCycle: 3, wPhaseShift_deg: >= 2 expected).
FLOAT_TOLERANCE = {
    "wDutyCycle": 1e-3,
    "wReferenceValue": 1e-3,
    "wPhaseShift_deg": 0.006,
    "wGain": 1e-5,
    "wOffset": 1e-5,
}

# Shield_Class measurement names -> Measurements/* objects
MEASUREMENTS = {
    "V1": "rV1Low_V",
    "V2": "rV2Low_V",
    "VH": "rVHigh_V",
    "I1": "rI1Low_A",
    "I2": "rI2Low_A",
    "IH": "rIHigh_A",
    "T1": "rTemp1_degC",
    "T2": "rTemp2_degC",
}

CALIBRATION_CHANNELS = ("V1", "V2", "VH", "I1", "I2", "IH")


class ThingSetShieldError(RuntimeError):
    """A command could not be mapped, sent, or verified."""


# ---------------------------------------------------------------------------
# argument helpers
# ---------------------------------------------------------------------------

def _leg(leg):
    """'LEG1'/'leg2'/1/2 -> 'Leg1'/'Leg2'."""
    key = str(leg).strip().upper()
    if key in ("LEG1", "1"):
        return "Leg1"
    if key in ("LEG2", "2"):
        return "Leg2"
    raise ValueError(f"unknown leg {leg!r} (expected LEG1 or LEG2)")


def _on_off(state):
    if isinstance(state, bool):
        return state
    key = str(state).strip().upper()
    if key in ("ON", "1", "TRUE"):
        return True
    if key in ("OFF", "0", "FALSE"):
        return False
    raise ValueError(f"unknown state {state!r} (expected ON or OFF)")


def _number(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return value


def _integer(name, value, minimum=None, maximum=None):
    value = _number(name, value)
    if value != round(value):
        raise ValueError(f"{name} must be a whole number, got {value!r}")
    value = int(round(value))
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ValueError(f"{name}={value} outside [{minimum}, {maximum}]")
    return value


# ---------------------------------------------------------------------------
# action -> list of (group path, {item: value}) writes
# ---------------------------------------------------------------------------

def _mode(name):
    return lambda: [("Config", {"Mode": MODES[name]})]


def _leg_bool(item):
    return lambda leg, state: [(f"Config/{_leg(leg)}", {item: _on_off(state)})]


def _duty(leg, value):
    value = _number("duty", value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"duty={value} outside [0, 1]")
    return [(f"Config/{_leg(leg)}", {"wDutyCycle": value})]


def _phase(leg, value):
    value = _number("phase shift", value)
    if not PHASE_MIN_DEG <= value <= PHASE_MAX_DEG:
        raise ValueError(f"phase shift={value} deg outside [{PHASE_MIN_DEG}, {PHASE_MAX_DEG}]")
    return [(f"Config/{_leg(leg)}", {"wPhaseShift_deg": value})]


def _dead_time(item):
    def build(leg, value):
        ns = _integer("dead time (ns)", value, DEAD_TIME_MIN_NS, DEAD_TIME_MAX_NS)
        return [(f"Config/{_leg(leg)}", {item: ns})]
    return build


def _frequency(leg, value):
    # The string protocol took a leg argument; the ThingSet firmware has one
    # global switching frequency. Keep validating the leg for typos.
    _leg(leg)
    return [("Config", {"Frequency_Hz": _integer("frequency (Hz)", value, minimum=1)})]


def _reference(leg, variable, value):
    group = f"Config/{_leg(leg)}"
    variable = str(variable).upper()
    if variable not in CALIBRATION_CHANNELS:
        raise ValueError(f"unknown tracking variable {variable!r}")
    return [(group, {"wTrackingVar": variable}),
            (group, {"wReferenceValue": _number("reference", value)})]


def _calibrate(variable, gain, offset):
    variable = str(variable).upper()
    if variable not in CALIBRATION_CHANNELS:
        raise ValueError(f"unknown calibration channel {variable!r}")
    group = f"Calibration/{variable}"
    return [(group, {"wGain": _number("gain", gain)}),
            (group, {"wOffset": _number("offset", offset)})]


def _dead_time_comp(state):
    return [("Config", {"wDeadTimeComp": _on_off(state)})]


ACTIONS = {
    "IDLE": _mode("IDLE"),
    "POWER_ON": _mode("POWER_ON"),
    "POWER_OFF": _mode("POWER_OFF"),
    "LEG": _leg_bool("wEnable"),
    "CAPA": _leg_bool("wCapa"),
    "DRIVER": _leg_bool("wDriver"),
    "BUCK": _leg_bool("wBuck"),
    "BOOST": _leg_bool("wBoost"),
    "DUTY": _duty,
    "FREQUENCY": _frequency,
    "DEAD_TIME_RISING": _dead_time("wDeadTimeRising_ns"),
    "DEAD_TIME_FALLING": _dead_time("wDeadTimeFalling_ns"),
    "PHASE_SHIFT": _phase,
    "DEADTIME_COMP": _dead_time_comp,
    "REFERENCE": _reference,
    "CALIBRATE": _calibrate,
}


def map_command(action, *args):
    """Return the ThingSet writes for a Shield_Class action, as a list of
    (group path, {item: value}). Raises ValueError on bad action/arguments."""
    try:
        build = ACTIONS[action]
    except KeyError:
        raise ValueError(f"Invalid action: {action}") from None
    try:
        return build(*args)
    except TypeError as exc:
        raise ValueError(f"bad arguments for {action}: {args!r} ({exc})") from exc


def _matches(item, actual, expected):
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual == expected
    if isinstance(expected, float):
        return (isinstance(actual, (int, float))
                and math.isclose(float(actual), expected, rel_tol=1e-6,
                                 abs_tol=FLOAT_TOLERANCE.get(item, 1e-6)))
    return actual == expected


# ---------------------------------------------------------------------------
# port selection
# ---------------------------------------------------------------------------

def _interface_number(info):
    """USB interface number of a pyserial ListPortInfo, or None.
    Linux/macOS location looks like '1-3.2:1.2', Windows '1-3:x.2'."""
    location = getattr(info, "location", None) or ""
    match = re.search(r":[^.:]*\.(\d+)$", location)
    return int(match.group(1)) if match else None


def _default_comports():
    from serial.tools import list_ports
    return list_ports.comports()


def _default_probe(device):
    from lib.thingset_tools import ThingSetTools
    client = ThingSetTools(device, baudrate=SAFE_BAUDRATE)
    client.close()
    return True


def find_thingset_port(vid=THINGSET_USB_VID, pid=THINGSET_USB_PID, serial_number=None,
                       by_id_dir=BY_ID_DIR, comports=None, probe=None):
    """Return the ThingSet-shell serial port of the board.

    1. Linux: the `/dev/serial/by-id/*-if02` link whose device has this
       VID/PID (and serial number, if given). Unique match required.
    2. Otherwise: the VID/PID port whose USB interface number is 2.
    3. Last resort: handshake probe (at 115200 baud) of the VID/PID ports
       whose interface number is unknown. Ports known to be if00 are never
       opened.
    Raises RuntimeError if nothing (or more than one board) matches.
    """
    ports = list(comports() if callable(comports) else (comports if comports is not None else _default_comports()))
    candidates = [p for p in ports
                  if p.vid == vid and p.pid == pid
                  and (serial_number is None or getattr(p, "serial_number", None) == serial_number)]
    by_device = {os.path.realpath(p.device): p for p in candidates}
    usb_ids = f"VID=0x{vid:04X} PID=0x{pid:04X}" + (f" serial={serial_number}" if serial_number else "")

    # 1. by-id links
    if by_id_dir and os.path.isdir(by_id_dir):
        links = sorted(glob.glob(os.path.join(by_id_dir, "*-if%02d" % THINGSET_INTERFACE)))
        links = [link for link in links if os.path.realpath(link) in by_device]
        if len(links) == 1:
            return links[0]
        if len(links) > 1:
            raise RuntimeError(
                f"{len(links)} ThingSet ports match {usb_ids}: {links}. "
                "Set 'shield_serial' (or 'shield_port') in the base config.")

    # 2. interface number from the USB location
    known = [(p, _interface_number(p)) for p in candidates]
    shells = [p.device for p, iface in known if iface == THINGSET_INTERFACE]
    if len(shells) == 1:
        return shells[0]
    if len(shells) > 1:
        raise RuntimeError(
            f"{len(shells)} ThingSet ports match {usb_ids}: {shells}. "
            "Set 'shield_serial' (or 'shield_port') in the base config.")

    # 3. probe the ports whose interface is unknown (never a known if00)
    probe = probe or _default_probe
    for p, iface in known:
        if iface is not None:
            continue
        try:
            if probe(p.device):
                return p.device
        except Exception:
            continue

    raise RuntimeError(f"no ThingSet shell port (if02) found for {usb_ids}")


# ---------------------------------------------------------------------------
# the shim
# ---------------------------------------------------------------------------

class ThingSetShield:
    """Shield_Device look-alike over ThingSet.

    `client` is any object with `read(path)` and `write(path, values)`
    (lib.thingset_tools.ThingSetTools on the bench, a fake in the tests).
    """

    def __init__(self, client, port=None, verify=True):
        self.client = client
        self.port = port
        self.verify = verify

    @classmethod
    def open(cls, port=None, vid=THINGSET_USB_VID, pid=THINGSET_USB_PID,
             serial_number=None, baudrate=SAFE_BAUDRATE, timeout=1.0, verify=True):
        """Find (unless given) and open the ThingSet port of the board."""
        if baudrate == BOOTLOADER_BAUDRATE:
            raise ValueError("1200 baud reboots the SPIN into MCUboot; refusing")
        if port is None:
            port = find_thingset_port(vid=vid, pid=pid, serial_number=serial_number)
        elif re.search(r"-if00$", str(port)):
            raise ValueError(f"{port} is the console (if00), not the ThingSet shell (if02)")
        from lib.thingset_tools import ThingSetTools
        client = ThingSetTools(port, baudrate=baudrate, timeout=timeout)
        return cls(client, port=port, verify=verify)

    @classmethod
    def from_config(cls, config):
        """Open from a base-config dict: optional 'shield_port',
        'shield_serial', 'shield_vid', 'shield_pid', 'shield_verify'."""
        return cls.open(
            port=config.get("shield_port") or None,
            vid=config.get("shield_vid", THINGSET_USB_VID),
            pid=config.get("shield_pid", THINGSET_USB_PID),
            serial_number=config.get("shield_serial") or None,
            verify=bool(config.get("shield_verify", True)),
        )

    def sendCommand(self, action, *args, delay=0.02):
        """Same signature as Shield_Device.sendCommand. Returns the request(s)
        as text, e.g. '=Config/Leg2 {"wPhaseShift_deg":12.0}'. Raises
        ValueError on a bad action/argument, ThingSetShieldError if the
        firmware rejects the write or reads back a different value."""
        writes = map_command(action, *args)
        sent = []
        for group, values in writes:
            try:
                self.client.write(group, values)
            except Exception as exc:
                raise ThingSetShieldError(f"{action} {args}: write {group} {values} failed: {exc}") from exc
            if self.verify:
                for item, expected in values.items():
                    path = f"{group}/{item}"
                    try:
                        actual = self.client.read(path)
                    except Exception as exc:
                        raise ThingSetShieldError(f"{action} {args}: readback of {path} failed: {exc}") from exc
                    if not _matches(item, actual, expected):
                        raise ThingSetShieldError(
                            f"{action} {args}: {path} reads back {actual!r}, requested {expected!r} "
                            "(the firmware restores rejected values)")
            sent.append(f"={group} " + ",".join(f'{{"{k}":{_text(v)}}}' for k, v in values.items()))
        if delay:
            time.sleep(delay)
        return "; ".join(sent)

    # ---- the rest of the Shield_Device surface the scripts touch ----------

    def getMeasurement(self, measurement_type):
        """Read one Measurements/* value ('V1', 'I2', 'VH', 'T1', ...)."""
        try:
            item = MEASUREMENTS[measurement_type]
        except KeyError:
            raise ValueError(f"Invalid measurement type {measurement_type!r}; "
                             f"supported: {', '.join(MEASUREMENTS)}") from None
        return float(self.client.read(f"Measurements/{item}"))

    def getLine(self, split_character=':'):
        """No frame stream on ThingSet: returns one snapshot of the
        Measurements group as ['name=value', ...] (split_character unused)."""
        values = self.client.read("Measurements")
        if not isinstance(values, dict):
            return [str(values)]
        return [f"{name}={value}" for name, value in values.items()]

    def resetSerialBuffer(self):
        """Nothing to flush: every ThingSet request reads its own answer."""

    def close(self):
        close = getattr(self.client, "close", None)
        if callable(close):
            close()


def _text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    return repr(value)
