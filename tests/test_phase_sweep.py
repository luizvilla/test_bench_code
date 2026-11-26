"""Run from the repository root: python -m unittest discover -s tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lib.phase_sweep import phase_sweep_values  # noqa: E402


class PhaseSweepTest(unittest.TestCase):
    def test_legacy_int_config_unchanged(self):
        # old generator: PhaseInit=min, PhaseFinal=int(last)+1, PhaseStep=int
        self.assertEqual(phase_sweep_values(10, 31, 10), list(range(10, 33, 10)))
        self.assertEqual(phase_sweep_values(0, 180, 30), list(range(0, 182, 30)))

    def test_float_sweep_inclusive_and_exact(self):
        # 10 kHz campaign point: lead-in 0, 0.5..3.5 A peak -> 2.4 deg steps up to 16.8
        vals = phase_sweep_values(0.0, 16.8, 2.4)
        self.assertEqual(vals, [0.0, 2.4, 4.8, 7.2, 9.6, 12.0, 14.4, 16.8])

    def test_float_sweep_no_overshoot(self):
        vals = phase_sweep_values(0.0, 168.0, 24.0)
        self.assertEqual(vals[-1], 168.0)
        self.assertEqual(len(vals), 8)
        # fractional step that does not divide evenly stops below final
        self.assertEqual(phase_sweep_values(1.0, 2.0, 0.3), [1.0, 1.3, 1.6, 1.9])

    def test_lead_in_below_first_point(self):
        vals = phase_sweep_values(0.0, 16.8, 2.4)
        self.assertLess(vals[0], vals[1])

    def test_bad_step(self):
        with self.assertRaises(ValueError):
            phase_sweep_values(0.0, 10.0, 0)


class GeneratorBoundsTest(unittest.TestCase):
    def test_phase_bounds(self):
        from Opposition_GenerateJson_v1_4 import phaseSweepBounds
        # 7 points 0.5..3.5 A at 10 kHz, 60 V, 40 uH -> 2.4..16.8 deg
        phases = [2.4 * k for k in range(1, 8)]
        self.assertEqual(phaseSweepBounds(phases), (0.0, 16.8, 2.4))
        # lead-in would be negative -> fall back to first point
        self.assertEqual(phaseSweepBounds([10.0, 30.0]), (10.0, 30.0, 20.0))


if __name__ == "__main__":
    unittest.main()
