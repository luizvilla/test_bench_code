"""Run from the repository root: python -m unittest discover -s tests

Scope 1 (PWM / inductor current) measures off screen: no measurement panel is shown
(it cluttered the waveforms), each frame is read with Cn:PAVA? <type> instead.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lib.SDS2104X_plus import SDS2104X_plus, parse_pava  # noqa: E402

MEASURES = [{"type": "FREQ", "channel": 1}, {"type": "AMPL", "channel": 2}, {"type": "RMS", "channel": 2}]


class FakeScope:
    def __init__(self, answers=None):
        self.writes, self.frame, self.answers = [], 0, answers or {}

    def write(self, cmd):
        self.writes.append(cmd)
        if cmd.startswith(":HISTORy:FRAMe "):
            self.frame = int(cmd.split()[-1])

    def query(self, cmd):
        self.writes.append(cmd)
        return self.answers.get((self.frame, cmd), "****")


def scope(answers=None):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"nbPointsI": 2, "ScopeAutoMeasure": MEASURES, "frequencyPWM": 50000}, f)
    try:
        s = SDS2104X_plus(f.name, ressource_manager=object())
    finally:
        os.unlink(f.name)
    s.oscilloscope = FakeScope(answers)
    return s


class ParsePavaTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(parse_pava("C1:PAVA FREQ,4.999719E+04Hz"), 49997.19)
        self.assertEqual(parse_pava("C2:PAVA AMPL,1.33E-01A\n"), 0.133)
        self.assertEqual(parse_pava("C2:PAVA RMS,5.37E-02A"), 0.0537)

    def test_no_value(self):
        self.assertIsNone(parse_pava("C1:PAVA FREQ,****"))


class FreeRunAfterCaptureTest(unittest.TestCase):
    """After a capture the scope goes back to AUTO (live), never left waiting in SINGLE."""

    def test_setup_clean_leaves_auto(self):
        s = scope()
        s.oscilloscope_setup_clean()
        w = s.oscilloscope.writes
        self.assertEqual([c for c in w if "TRIG:MODE" in c.upper().replace("TRIGGER", "TRIG")][-1].split()[-1].upper(), "AUTO")
        self.assertIn(":ACQuire:SEQuence OFF", w)
        self.assertIn(":HISTORy OFF", w)

    def test_free_run(self):
        s = scope()
        s.free_run()
        self.assertEqual(s.oscilloscope.writes, [":ACQuire:SEQuence OFF", ":HISTORy OFF", ":TRIGger:MODE AUTO"])


class OffScreenMeasureTest(unittest.TestCase):
    def test_setup_shows_no_measurement_panel(self):
        s = scope()
        s.oscilloscope_setup()
        w = s.oscilloscope.writes
        self.assertIn(":MEASure OFF", w)
        self.assertNotIn(":MEASure ON", w)
        self.assertFalse(any(c.startswith(":MEASure:ADVanced:P") for c in w))

    def test_each_frame_read_with_pava(self):
        answers = {
            (1, "C1:PAVA? FREQ"): "C1:PAVA FREQ,5.00E+04Hz",
            (1, "C2:PAVA? AMPL"): "C2:PAVA AMPL,1.00E+00A",
            (1, "C2:PAVA? RMS"): "C2:PAVA RMS,2.90E-01A",
            (2, "C1:PAVA? FREQ"): "C1:PAVA FREQ,5.00E+04Hz",
            (2, "C2:PAVA? AMPL"): "C2:PAVA AMPL,2.00E+00A",
            (2, "C2:PAVA? RMS"): "C2:PAVA RMS,****",
        }
        s = scope(answers)
        with tempfile.TemporaryDirectory() as d:
            s.result_output_path = d
            s.oscilloscope_save_results()
            res = json.load(open(os.path.join(d, "results.json")))
        self.assertEqual(res["Data1"]["2"], {"type": "AMPL", "channel": 2, "value": 1.0})
        self.assertEqual(res["Data2"]["2"]["value"], 2.0)
        self.assertIsNone(res["Data2"]["3"]["value"])
        self.assertEqual(res["Data1"]["1"]["value"], 50000.0)


if __name__ == "__main__":
    unittest.main()
