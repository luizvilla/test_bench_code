"""Run from the repository root: python -m unittest discover -s tests

single_point_manual: the phase before the step must be below the measurement phase.
At 10 kHz / 0.5 A the measurement phase is 2.4 deg, below the configs' 3 deg initial phase.
"""

import importlib.util
import os
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
spec = importlib.util.spec_from_file_location("single_point_manual", os.path.join(ROOT, "tools", "single_point_manual.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


class SinglePointPhaseTest(unittest.TestCase):
    def test_phase_formula(self):
        self.assertEqual(sp.phase_for(0.5, 40, 10000, 60), 2.4)
        self.assertEqual(sp.phase_for(0.5, 40, 50000, 60), 12.0)

    def test_initial_kept_when_well_below(self):
        self.assertEqual(sp.initial_phase(3, 12.0), 3)

    def test_initial_lowered_to_half_the_step(self):
        self.assertEqual(sp.initial_phase(3, 2.4), 1.2)
        self.assertEqual(sp.initial_phase(3, 4.8), 2.4)

    def test_explicit_initial_wins_but_must_be_below(self):
        self.assertEqual(sp.initial_phase(3, 2.4, requested=0.0), 0.0)
        with self.assertRaises(ValueError):
            sp.initial_phase(3, 2.4, requested=2.4)

    def test_il_mean_added_once(self):
        base = [{"type": "FREQ", "channel": 1}, {"type": "AMPL", "channel": 2}, {"type": "RMS", "channel": 2}]
        m = sp.with_il_mean(base)
        self.assertEqual(m[-1], {"type": "MEAN", "channel": 2})
        self.assertEqual(len(m), 4)
        self.assertEqual(sp.with_il_mean(m), m)
        self.assertEqual(len(base), 3)   # input untouched

    def test_dtc_modes(self):
        # (DeadTimeComp at setup, DMM bursts)
        self.assertEqual(sp.dtc_plan("off"), (0, 2))
        self.assertEqual(sp.dtc_plan("on"), (1, 2))
        self.assertEqual(sp.dtc_plan("ab"), (0, 3))
        with self.assertRaises(ValueError):
            sp.dtc_plan("maybe")

    def test_default_frequency_is_10_khz(self):
        self.assertEqual(sp.DEFAULT_FREQ, 10000)


if __name__ == "__main__":
    unittest.main()
