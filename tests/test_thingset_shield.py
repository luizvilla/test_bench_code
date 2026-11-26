"""Tests for lib/thingset_shield.py and the supervisor protocol switch (#16).

No hardware: a fake ThingSet client records writes and answers readbacks.
Run: python3 -m unittest discover -s tests   (or pytest tests)
"""

import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import thingset_shield as ts  # noqa: E402
from lib.thingset_shield import ThingSetShield, ThingSetShieldError, find_thingset_port  # noqa: E402


class FakeThingSetClient:
    """read(path)/write(path, values) like ThingSetTools, backed by a dict.
    `reject` maps a full item path to the value the firmware restores."""

    def __init__(self, reject=None, fail_write=None):
        self.store = {}
        self.writes = []
        self.reads = []
        self.reject = reject or {}
        self.fail_write = fail_write
        self.closed = False

    def write(self, path, values):
        if self.fail_write:
            raise self.fail_write
        self.writes.append((path, dict(values)))
        for item, value in values.items():
            full = f"{path}/{item}"
            self.store[full] = self.reject.get(full, value)
        return True

    def read(self, path):
        self.reads.append(path)
        if path in self.store:
            return self.store[path]
        prefix = path + "/"
        group = {k[len(prefix):]: v for k, v in self.store.items() if k.startswith(prefix)}
        if group:
            return group
        raise KeyError(path)

    def close(self):
        self.closed = True


# action, args -> expected writes [(group, {item: value})]
MAPPING = [
    ("IDLE", (), [("Config", {"Mode": 0})]),
    ("POWER_ON", (), [("Config", {"Mode": 1})]),
    ("POWER_OFF", (), [("Config", {"Mode": 2})]),
    ("LEG", ("LEG1", "ON"), [("Config/Leg1", {"wEnable": True})]),
    ("LEG", ("LEG2", "OFF"), [("Config/Leg2", {"wEnable": False})]),
    ("CAPA", ("LEG1", "ON"), [("Config/Leg1", {"wCapa": True})]),
    ("DRIVER", ("LEG2", "OFF"), [("Config/Leg2", {"wDriver": False})]),
    ("BUCK", ("LEG1", "ON"), [("Config/Leg1", {"wBuck": True})]),
    ("BOOST", ("LEG2", "ON"), [("Config/Leg2", {"wBoost": True})]),
    ("DUTY", ("LEG1", 0.5), [("Config/Leg1", {"wDutyCycle": 0.5})]),
    ("DUTY", ("LEG2", 0.437), [("Config/Leg2", {"wDutyCycle": 0.437})]),
    ("FREQUENCY", ("LEG1", 50000), [("Config", {"Frequency_Hz": 50000})]),
    ("DEAD_TIME_RISING", ("LEG2", 300), [("Config/Leg2", {"wDeadTimeRising_ns": 300})]),
    ("DEAD_TIME_FALLING", ("LEG1", 300), [("Config/Leg1", {"wDeadTimeFalling_ns": 300})]),
    ("PHASE_SHIFT", ("LEG2", 3), [("Config/Leg2", {"wPhaseShift_deg": 3.0})]),
    ("PHASE_SHIFT", ("LEG2", 14.64), [("Config/Leg2", {"wPhaseShift_deg": 14.64})]),
    ("PHASE_SHIFT", ("LEG1", 0.0), [("Config/Leg1", {"wPhaseShift_deg": 0.0})]),
    ("DEADTIME_COMP", ("ON",), [("Config", {"wDeadTimeComp": True})]),
    ("DEADTIME_COMP", ("OFF",), [("Config", {"wDeadTimeComp": False})]),
    ("REFERENCE", ("LEG1", "V1", 12.5),
     [("Config/Leg1", {"wTrackingVar": "V1"}), ("Config/Leg1", {"wReferenceValue": 12.5})]),
    ("CALIBRATE", ("I1", 0.005, -10.0),
     [("Calibration/I1", {"wGain": 0.005}), ("Calibration/I1", {"wOffset": -10.0})]),
]


class TestActionMapping(unittest.TestCase):

    def test_every_action_is_covered(self):
        self.assertEqual({a for a, _, _ in MAPPING}, set(ts.ACTIONS))

    def test_mapping(self):
        for action, args, expected in MAPPING:
            with self.subTest(action=action, args=args):
                client = FakeThingSetClient()
                shield = ThingSetShield(client)
                msg = shield.sendCommand(action, *args, delay=0)
                self.assertEqual(client.writes, expected)
                # every written item is read back individually
                self.assertEqual(client.reads, [f"{g}/{k}" for g, v in expected for k in v])
                self.assertTrue(msg.startswith("=" + expected[0][0]))

    def test_types_on_the_wire(self):
        client = FakeThingSetClient()
        shield = ThingSetShield(client)
        shield.sendCommand("PHASE_SHIFT", "LEG2", 12, delay=0)
        shield.sendCommand("FREQUENCY", "LEG1", 60000.0, delay=0)
        shield.sendCommand("DEAD_TIME_RISING", "LEG1", 300.0, delay=0)
        phase = client.writes[0][1]["wPhaseShift_deg"]
        self.assertIsInstance(phase, float)                       # float object, not int16 wPhaseShift
        self.assertIs(type(client.writes[1][1]["Frequency_Hz"]), int)
        self.assertIs(type(client.writes[2][1]["wDeadTimeRising_ns"]), int)
        self.assertNotIn("wPhaseShift", client.writes[0][1])

    def test_leg_and_state_spelling(self):
        client = FakeThingSetClient()
        shield = ThingSetShield(client)
        shield.sendCommand("LEG", "leg2", "on", delay=0)
        shield.sendCommand("CAPA", 1, True, delay=0)
        self.assertEqual(client.writes, [("Config/Leg2", {"wEnable": True}),
                                         ("Config/Leg1", {"wCapa": True})])

    def test_bad_input_raises_before_sending(self):
        bad = [
            ("NOPE", ()),
            ("LEG", ("LEG3", "ON")),
            ("LEG", ("LEG1", "MAYBE")),
            ("LEG", ("LEG1",)),
            ("DUTY", ("LEG1", 1.2)),
            ("DUTY", ("LEG1", "0.5")),
            ("PHASE_SHIFT", ("LEG2", -1)),
            ("PHASE_SHIFT", ("LEG2", 361)),
            ("PHASE_SHIFT", ("LEG2", float("nan"))),
            ("DEAD_TIME_RISING", ("LEG1", 30)),
            ("DEAD_TIME_FALLING", ("LEG1", 2500)),
            ("DEAD_TIME_FALLING", ("LEG1", 300.5)),
            ("FREQUENCY", ("LEG1", [50000, 60000])),
            ("FREQUENCY", ("LEG1", 0)),
            ("DEADTIME_COMP", ("SOMETIMES",)),
            ("CALIBRATE", ("XX", 1.0, 0.0)),
        ]
        for action, args in bad:
            with self.subTest(action=action, args=args):
                client = FakeThingSetClient()
                with self.assertRaises(ValueError):
                    ThingSetShield(client).sendCommand(action, *args, delay=0)
                self.assertEqual(client.writes, [])

    def test_firmware_restore_is_an_error(self):
        client = FakeThingSetClient(reject={"Config/Leg2/wDutyCycle": 0.5})
        with self.assertRaises(ThingSetShieldError):
            ThingSetShield(client).sendCommand("DUTY", "LEG2", 0.7, delay=0)

    def test_float_readback_tolerance(self):
        # firmware serialises the phase with 2 decimals
        client = FakeThingSetClient(reject={"Config/Leg2/wPhaseShift_deg": 14.64})
        ThingSetShield(client).sendCommand("PHASE_SHIFT", "LEG2", 14.6400001, delay=0)
        client = FakeThingSetClient(reject={"Config/Leg2/wPhaseShift_deg": 14.0})
        with self.assertRaises(ThingSetShieldError):
            ThingSetShield(client).sendCommand("PHASE_SHIFT", "LEG2", 14.64, delay=0)

    def test_write_error_raises(self):
        client = FakeThingSetClient(fail_write=RuntimeError("0xA4 Not Found"))
        with self.assertRaises(ThingSetShieldError):
            ThingSetShield(client).sendCommand("DEADTIME_COMP", "ON", delay=0)

    def test_verify_off_skips_readback(self):
        client = FakeThingSetClient()
        ThingSetShield(client, verify=False).sendCommand("POWER_ON", delay=0)
        self.assertEqual(client.reads, [])

    def test_delay_is_kept(self):
        with mock.patch.object(ts.time, "sleep") as sleep:
            ThingSetShield(FakeThingSetClient()).sendCommand("IDLE", delay=0.6)
        sleep.assert_called_once_with(0.6)

    def test_other_shield_methods(self):
        client = FakeThingSetClient()
        client.store.update({"Measurements/rV1Low_V": 12.3, "Measurements/rI2Low_A": -0.4})
        shield = ThingSetShield(client)
        self.assertEqual(shield.getMeasurement("V1"), 12.3)
        self.assertEqual(sorted(shield.getLine()), ["rI2Low_A=-0.4", "rV1Low_V=12.3"])
        with self.assertRaises(ValueError):
            shield.getMeasurement("ZZ")
        shield.resetSerialBuffer()
        shield.close()
        self.assertTrue(client.closed)


def _port(device, vid=0x2FE3, pid=0x0100, serial="5843500300470031", location=None):
    return types.SimpleNamespace(device=device, vid=vid, pid=pid, serial_number=serial, location=location)


class TestPortSelection(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dev = os.path.join(self.tmp.name, "dev")
        self.by_id = os.path.join(self.tmp.name, "by-id")
        os.makedirs(self.dev)
        os.makedirs(self.by_id)

    def tearDown(self):
        self.tmp.cleanup()

    def _tty(self, name, link=None):
        path = os.path.join(self.dev, name)
        open(path, "w").close()
        if link:
            os.symlink(path, os.path.join(self.by_id, link))
        return path

    def _no_probe(self, device):
        raise AssertionError(f"probe must not run (opened {device})")

    def test_by_id_if02(self):
        acm3 = self._tty("ttyACM3", "usb-OwnTech_Technologies_SPIN_5843500300470031-if00")
        acm4 = self._tty("ttyACM4", "usb-OwnTech_Technologies_SPIN_5843500300470031-if02")
        stl = self._tty("ttyACM9", "usb-STMicroelectronics_STLINK-V3_001E-if02")
        ports = [_port(acm3), _port(acm4), _port(stl, vid=0x0483, pid=0x374E)]
        got = find_thingset_port(by_id_dir=self.by_id, comports=ports, probe=self._no_probe)
        self.assertEqual(got, os.path.join(self.by_id, "usb-OwnTech_Technologies_SPIN_5843500300470031-if02"))

    def test_two_boards_need_a_serial(self):
        ports = []
        for sn, (a, b) in {"5843500300470031": ("ttyACM3", "ttyACM4"),
                           "5843500300470041": ("ttyACM1", "ttyACM2")}.items():
            ports.append(_port(self._tty(a, f"usb-OwnTech_Technologies_SPIN_{sn}-if00"), serial=sn))
            ports.append(_port(self._tty(b, f"usb-OwnTech_Technologies_SPIN_{sn}-if02"), serial=sn))
        with self.assertRaises(RuntimeError) as ctx:
            find_thingset_port(by_id_dir=self.by_id, comports=ports, probe=self._no_probe)
        self.assertIn("shield_serial", str(ctx.exception))
        got = find_thingset_port(serial_number="5843500300470041", by_id_dir=self.by_id,
                                 comports=ports, probe=self._no_probe)
        self.assertTrue(got.endswith("SPIN_5843500300470041-if02"))

    def test_old_string_pid_is_not_taken(self):
        acm4 = self._tty("ttyACM4", "usb-OwnTech_Technologies_COMM-MASTER_1-if02")
        with self.assertRaises(RuntimeError):
            find_thingset_port(by_id_dir=self.by_id, comports=[_port(acm4, pid=0x0101)],
                               probe=self._no_probe)

    def test_fallback_on_usb_interface_number(self):
        ports = [_port("COM3", location="1-3:x.0"), _port("COM4", location="1-3:x.2")]
        got = find_thingset_port(by_id_dir=os.path.join(self.tmp.name, "absent"),
                                 comports=ports, probe=self._no_probe)
        self.assertEqual(got, "COM4")
        ports = [_port("/dev/ttyACM0", location="1-1.4:1.0"), _port("/dev/ttyACM1", location="1-1.4:1.2")]
        self.assertEqual(find_thingset_port(by_id_dir=None, comports=ports, probe=self._no_probe),
                         "/dev/ttyACM1")

    def test_probe_last_resort_skips_known_if00(self):
        probed = []

        def probe(device):
            probed.append(device)
            if device == "/dev/cu.usbmodem2":
                return True
            raise TimeoutError("no shell")

        ports = [_port("/dev/known_if00", location="1-1:1.0"),
                 _port("/dev/cu.usbmodem1"), _port("/dev/cu.usbmodem2")]
        got = find_thingset_port(by_id_dir=None, comports=ports, probe=probe)
        self.assertEqual(got, "/dev/cu.usbmodem2")
        self.assertEqual(probed, ["/dev/cu.usbmodem1", "/dev/cu.usbmodem2"])

    def test_nothing_found(self):
        with self.assertRaises(RuntimeError):
            find_thingset_port(by_id_dir=None, comports=[], probe=self._no_probe)

    def test_open_refuses_if00_and_1200_baud(self):
        with self.assertRaises(ValueError):
            ThingSetShield.open(port="/dev/serial/by-id/usb-OwnTech_Technologies_SPIN_1-if00")
        with self.assertRaises(ValueError):
            ThingSetShield.open(port="/dev/ttyACM4", baudrate=1200)

    def test_open_uses_115200_on_the_selected_port(self):
        fake_mod = types.ModuleType("lib.thingset_tools")
        calls = []

        class FakeTools:
            def __init__(self, port, baudrate, timeout):
                calls.append((port, baudrate))

        fake_mod.ThingSetTools = FakeTools
        with mock.patch.dict(sys.modules, {"lib.thingset_tools": fake_mod}), \
                mock.patch.object(ts, "find_thingset_port", return_value="/dev/by-id/x-if02") as find:
            shield = ThingSetShield.from_config({"shield_vid": 12259, "shield_pid": 256,
                                                 "shield_serial": "5843500300470031"})
        find.assert_called_once_with(vid=12259, pid=256, serial_number="5843500300470031")
        self.assertEqual(calls, [("/dev/by-id/x-if02", 115200)])
        self.assertEqual(shield.port, "/dev/by-id/x-if02")


class TestSupervisorProtocolSwitch(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            import supervisor_class  # noqa: F401
        except ImportError as exc:  # pyvisa/serial/matplotlib missing
            raise unittest.SkipTest(f"supervisor_class not importable: {exc}")
        cls.sc = sys.modules["supervisor_class"]

    def _supervisor(self, **extra):
        root = os.path.join(os.path.dirname(__file__), "..")
        with open(os.path.join(root, "sessions/2026-11-27/configs/A_anchors/PhaseShift/"
                               "Voltage_60_50kHz/PhaseShift_Voltage_60V_Freq50kHz.json")) as f:
            config = json.load(f)
        for key in ("shield_protocol", "DeadTimeComp"):
            config.pop(key, None)
        config.update(extra)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config["dataOutputFolder"] = os.path.join(tmp.name, "out")
        path = os.path.join(tmp.name, "config.json")
        with open(path, "w") as f:
            json.dump(config, f)
        with mock.patch("builtins.print"):
            return self.sc.Supervisor(path, sds_oscilloscope=mock.Mock())

    def test_default_is_string_protocol(self):
        sup = self._supervisor()
        self.assertEqual(sup.shield_protocol, "string")
        with mock.patch.object(self.sc.find_devices, "find_shield_device_ports", return_value=["/dev/ttyACM0"]) as find, \
                mock.patch.object(self.sc, "Shield_Device") as device, \
                mock.patch.object(self.sc.ThingSetShield, "from_config") as thingset, \
                mock.patch("builtins.print"):
            sup.open_microcontroller()
        find.assert_called_once()
        device.assert_called_once_with(shield_port="/dev/ttyACM0", shield_type="TWIST")
        thingset.assert_not_called()

    def test_thingset_protocol(self):
        sup = self._supervisor(shield_protocol="thingset", shield_pid=256)
        fake = ThingSetShield(FakeThingSetClient(), port="/dev/by-id/x-if02")
        with mock.patch.object(self.sc.ThingSetShield, "from_config", return_value=fake) as thingset, \
                mock.patch.object(self.sc.find_devices, "find_shield_device_ports") as find, \
                mock.patch("builtins.print"):
            sup.open_microcontroller()
        thingset.assert_called_once_with(sup.config)
        find.assert_not_called()
        self.assertIs(sup.microcontroller, fake)

    def test_bad_protocol(self):
        with self.assertRaises(ValueError):
            self._supervisor(shield_protocol="can")

    def _setup_writes(self, **extra):
        sup = self._supervisor(shield_protocol="thingset", **extra)
        client = FakeThingSetClient()
        sup.microcontroller = ThingSetShield(client)
        with mock.patch("builtins.print"), mock.patch.object(ts.time, "sleep"):
            sup.microcontroller_setup()
            sup.microcontroller_sweep_phase_shift(0.0, 24.0, 12.0)
        return client.writes

    def test_setup_and_sweep_end_to_end(self):
        writes = self._setup_writes(DeadTimeComp=1)
        self.assertEqual(writes, [
            ("Config/Leg1", {"wEnable": True}),
            ("Config/Leg2", {"wEnable": True}),
            ("Config", {"Mode": 1}),
            ("Config/Leg1", {"wDutyCycle": 0.5}),
            ("Config/Leg2", {"wDutyCycle": 0.5}),
            ("Config", {"Frequency_Hz": 50000}),
            ("Config/Leg2", {"wDeadTimeRising_ns": 300}),
            ("Config/Leg1", {"wDeadTimeRising_ns": 300}),
            ("Config/Leg2", {"wDeadTimeFalling_ns": 300}),
            ("Config/Leg1", {"wDeadTimeFalling_ns": 300}),
            ("Config", {"wDeadTimeComp": True}),
            ("Config/Leg2", {"wPhaseShift_deg": 3.0}),
            ("Config/Leg2", {"wPhaseShift_deg": 0.0}),
            ("Config/Leg2", {"wPhaseShift_deg": 12.0}),
            ("Config/Leg2", {"wPhaseShift_deg": 24.0}),
        ])

    def test_dead_time_comp_off_and_absent(self):
        self.assertIn(("Config", {"wDeadTimeComp": False}), self._setup_writes(DeadTimeComp=0))
        self.assertFalse(any("wDeadTimeComp" in v for _, v in self._setup_writes()))

    def test_dead_time_comp_needs_thingset(self):
        sup = self._supervisor(DeadTimeComp=1)
        sup.microcontroller = mock.Mock()
        with mock.patch("builtins.print"), self.assertRaises(ValueError):
            sup.microcontroller_setup()

    def test_session_configs_use_thingset(self):
        root = os.path.join(os.path.dirname(__file__), "..", "sessions", "2026-11-27")
        # base configs and generated run configs only: not the dry-run reports nor the results.json of a run
        paths = [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs
                 if f.endswith(".json") and f.startswith(("base-config", "PhaseShift_", "DutyShift_"))]
        self.assertGreater(len(paths), 2)
        for path in paths:
            with open(path) as f:
                config = json.load(f)
            with self.subTest(path=os.path.relpath(path, root)):
                self.assertEqual(config.get("shield_protocol"), "thingset")
                self.assertEqual(config.get("shield_pid"), ts.THINGSET_USB_PID)
                self.assertEqual(config.get("shield_vid"), ts.THINGSET_USB_VID)
                self.assertIn(config.get("DeadTimeComp"), (0, 1))


if __name__ == "__main__":
    unittest.main()
