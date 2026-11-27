"""Run from the repository root: python -m unittest discover -s tests"""
import importlib.util, os, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
spec = importlib.util.spec_from_file_location("offset_sweep", os.path.join(ROOT, "tools", "offset_sweep.py"))
os_ = importlib.util.module_from_spec(spec); spec.loader.exec_module(os_)


class OffsetSweepTest(unittest.TestCase):
    def test_sweep_points_symmetric_with_zero(self):
        p = os_.sweep_points(0.004, 9)
        self.assertEqual(p[0], -0.004); self.assertEqual(p[-1], 0.004); self.assertIn(0.0, p); self.assertEqual(len(p), 9)

    def test_fit_zero(self):
        a, b, x0 = os_.fit_zero([-0.002, 0.0, 0.002], [-0.1, 0.18, 0.46])
        self.assertAlmostEqual(a, 140.0); self.assertAlmostEqual(b, 0.18); self.assertAlmostEqual(x0, -0.18 / 140)

    def test_fit_zero_ignores_missing(self):
        self.assertEqual(os_.fit_zero([0, 1], [None, 2.0]), (None, None, None))

    def test_scope_scale_holds_peak_plus_offset(self):
        # 3.5 A + the 0.005 sweep's offset (86 A/duty * 0.0025 = 0.215 A) + margin
        self.assertGreater(os_.scope_imax(3.5, 0.005), 3.5 + 0.215)
        self.assertLess(os_.scope_imax(0.5, 0.005), 1.5)

    def test_phase(self):
        self.assertEqual(os_.phase_for(2.0, 40, 50000, 60), 48.0)
        self.assertEqual(os_.phase_for(2.0, 40, 100000, 60), 96.0)


if __name__ == "__main__":
    unittest.main()
