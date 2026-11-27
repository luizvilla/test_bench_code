"""Run from the repository root: python -m unittest discover -s tests

Automatic detection of the TDK-Lambda Z+ supply. It is found by its USB vendor ID
(0x2504), never by sending text to other serial ports (the SPIN shares ttyACM*), and
it is selected with INST:NSEL before *IDN?: a Z+ ignores every command until its
address is selected, so a bare *IDN? misses it after each power cycle.
"""

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lib.TDKZ650_1_U import TDKZ650_1_U, find_tdk_ports  # noqa: E402

SPIN_CONSOLE = SimpleNamespace(device="/dev/ttyACM0", vid=0x2FE3, pid=0x0100)
SPIN_THINGSET = SimpleNamespace(device="/dev/ttyACM1", vid=0x2FE3, pid=0x0100)
TDK = SimpleNamespace(device="/dev/ttyACM2", vid=0x2504, pid=0x0001)
NO_USB = SimpleNamespace(device="/dev/ttyS0", vid=None, pid=None)


class FakeSupply:
    """A Z+ on the wire: answers only once INST:NSEL <address> was received."""

    def __init__(self, address=1, idn="TDK-LAMBDA,Z650-1,320B334-0005,3.002"):
        self.address, self.idn, self.selected, self.writes = address, idn, False, []

    def write(self, cmd):
        self.writes.append(cmd)
        parts = cmd.split()
        if parts[0].upper().startswith("INST") and int(parts[-1]) == self.address:
            self.selected = True

    def query(self, cmd):
        self.write(cmd)
        if not self.selected:
            raise TimeoutError("no answer")
        return self.idn if cmd.startswith("*IDN") else "0"

    def close(self):
        pass


class FakeRM:
    def __init__(self, devices):
        self.devices, self.opened = devices, []

    def open_resource(self, name, **kw):
        self.opened.append(name)
        if name not in self.devices:
            raise OSError(f"no such port {name}")
        return self.devices[name]


def supply(rm, ports, config_name="ASRL/dev/serial/by-id/fallback::INSTR"):
    psu = TDKZ650_1_U(config_path=None, ressource_manager=rm)
    psu.hv_power_supply_name = config_name
    psu.comports = lambda: ports
    return psu


class FindTdkPortsTest(unittest.TestCase):
    def test_only_tdk_vendor_id(self):
        self.assertEqual(find_tdk_ports([SPIN_CONSOLE, SPIN_THINGSET, TDK, NO_USB]), ["/dev/ttyACM2"])

    def test_none(self):
        self.assertEqual(find_tdk_ports([SPIN_CONSOLE, NO_USB]), [])


class OpenSupplyTest(unittest.TestCase):
    def test_found_after_power_cycle(self):
        z = FakeSupply()  # not selected: a bare *IDN? would time out
        rm = FakeRM({"ASRL/dev/ttyACM2::INSTR": z})
        psu = supply(rm, [SPIN_CONSOLE, SPIN_THINGSET, TDK])
        psu.open_hv_power_supply()
        self.assertEqual(psu.hv_power_supply_name, "ASRL/dev/ttyACM2::INSTR")
        self.assertIs(psu.hv_power_supply, z)
        self.assertLess(z.writes.index("INSTrument:NSELect 1"), z.writes.index("*IDN?"))

    def test_never_writes_to_spin_ports(self):
        rm = FakeRM({"ASRL/dev/ttyACM2::INSTR": FakeSupply()})
        supply(rm, [SPIN_CONSOLE, SPIN_THINGSET, TDK]).open_hv_power_supply()
        self.assertNotIn("ASRL/dev/ttyACM0::INSTR", rm.opened)
        self.assertNotIn("ASRL/dev/ttyACM1::INSTR", rm.opened)

    def test_no_supply_raises_instead_of_using_another_port(self):
        rm = FakeRM({})
        psu = supply(rm, [SPIN_CONSOLE, SPIN_THINGSET])
        with self.assertRaises(RuntimeError):
            psu.open_hv_power_supply()
        self.assertIsNone(psu.hv_power_supply)

    def test_config_name_used_when_it_answers(self):
        # no USB match (e.g. RS-232 adapter): the configured port is tried, and must identify as TDK
        z = FakeSupply()
        rm = FakeRM({"ASRL/dev/serial/by-id/fallback::INSTR": z})
        psu = supply(rm, [SPIN_CONSOLE])
        psu.open_hv_power_supply()
        self.assertIs(psu.hv_power_supply, z)

    def test_config_name_that_is_not_a_tdk_is_refused(self):
        not_tdk = FakeSupply(idn="OwnTech,SPIN")
        rm = FakeRM({"ASRL/dev/serial/by-id/fallback::INSTR": not_tdk})
        with self.assertRaises(RuntimeError):
            supply(rm, [SPIN_CONSOLE]).open_hv_power_supply()


if __name__ == "__main__":
    unittest.main()
