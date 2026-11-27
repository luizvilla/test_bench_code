"""Run from the repository root: python -m unittest discover -s tests

Differential duty trim (config "DutyTrimDiff" = D1 - D2): cancels the inductor-current DC offset
measured on 27 Nov (offset_sweep: zero at Delta = -0.0002..-0.0006 over 50/100 kHz x 0.5..3.5 A).
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from lib.duty_trim import leg_duties  # noqa: E402

CFG = os.path.join(ROOT, "sessions/2026-11-27/configs/A_anchors/PhaseShift/Voltage_60_50kHz/"
                         "PhaseShift_Voltage_60V_Freq50kHz.json")


class LegDutiesTest(unittest.TestCase):
    def test_no_trim(self):
        self.assertEqual(leg_duties(0.5), (0.5, 0.5))
        self.assertEqual(leg_duties(0.5, 0.0), (0.5, 0.5))

    def test_trim_is_d1_minus_d2_centred(self):
        d1, d2 = leg_duties(0.5, -0.0004)
        self.assertAlmostEqual(d1, 0.4998)
        self.assertAlmostEqual(d2, 0.5002)
        self.assertAlmostEqual(d1 - d2, -0.0004)
        self.assertAlmostEqual((d1 + d2) / 2, 0.5)

    def test_cutoff_frequency(self):
        # at 100 kHz 0.0002 per leg is below one timer tick: no trim above the cutoff
        self.assertEqual(leg_duties(0.5, -0.0004, freq=100000, max_freq=60000), (0.5, 0.5))
        self.assertEqual(leg_duties(0.5, -0.0004, freq=50000, max_freq=60000), (0.4998, 0.5002))
        self.assertEqual(leg_duties(0.5, -0.0004, freq=60000, max_freq=60000), (0.4998, 0.5002))
        self.assertEqual(leg_duties(0.5, -0.0004, freq=100000), (0.4998, 0.5002))   # no cutoff given

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            leg_duties(0.5, 0.2)     # 10 % per leg: a typo, not a trim


class SupervisorTrimTest(unittest.TestCase):
    def setUp(self):
        try:
            import supervisor_class
        except ImportError as exc:
            raise unittest.SkipTest(f"supervisor_class not importable: {exc}")
        self.sc = supervisor_class

    def _setup_writes(self, **extra):
        config = json.load(open(CFG))
        config.pop("DutyTrimDiff", None)
        config.update(extra)
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        config["dataOutputFolder"] = os.path.join(tmp.name, "out")
        path = os.path.join(tmp.name, "config.json"); json.dump(config, open(path, "w"))
        with mock.patch("builtins.print"):
            sup = self.sc.Supervisor(path, sds_oscilloscope=mock.Mock())
        sup.microcontroller = mock.Mock()
        with mock.patch("builtins.print"):
            sup.microcontroller_setup()
        return [c.args for c in sup.microcontroller.sendCommand.call_args_list if c.args[0] == "DUTY"]

    def test_default_untrimmed(self):
        self.assertEqual(self._setup_writes(), [("DUTY", "LEG1", 0.5), ("DUTY", "LEG2", 0.5)])

    def test_trim_applied(self):
        writes = self._setup_writes(DutyTrimDiff=-0.0004)
        self.assertEqual([w[1] for w in writes], ["LEG1", "LEG2"])
        self.assertAlmostEqual(writes[0][2], 0.4998)
        self.assertAlmostEqual(writes[1][2], 0.5002)

    def test_trim_off_above_cutoff(self):
        writes = self._setup_writes(DutyTrimDiff=-0.0004, DutyTrimMaxFreq=60000, frequencyPWM=100000)
        self.assertEqual([w[2] for w in writes], [0.5, 0.5])

    def test_grid_configs_carry_the_trim(self):
        # B_grid regenerated with the trim; A_anchors kept as run (no trim) since its results exist
        grid = os.path.join(ROOT, "sessions/2026-11-27/configs/B_grid/PhaseShift/Voltage_60_50kHz/"
                                  "PhaseShift_Voltage_60V_Freq50kHz.json")
        cfg = json.load(open(grid))
        self.assertAlmostEqual(cfg["DutyTrimDiff"], -0.0004)
        self.assertEqual(cfg["DutyTrimMaxFreq"], 60000)


if __name__ == "__main__":
    unittest.main()
