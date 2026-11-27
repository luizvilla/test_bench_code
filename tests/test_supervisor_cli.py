"""Run from the repository root: python -m unittest discover -s tests

supervisor_script command line: optional base-config path, optional --fast
(no scope-1 frame screenshots, no 5 s plot pause; measurements unchanged).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from supervisor_script import parse_cli  # noqa: E402


class SupervisorCliTest(unittest.TestCase):
    def test_default(self):
        self.assertEqual(parse_cli([]), ("base-config.json", False))

    def test_base_config(self):
        self.assertEqual(parse_cli(["s/base-config_B_grid.json"]), ("s/base-config_B_grid.json", False))

    def test_fast_either_order(self):
        self.assertEqual(parse_cli(["s/b.json", "--fast"]), ("s/b.json", True))
        self.assertEqual(parse_cli(["--fast", "s/b.json"]), ("s/b.json", True))
        self.assertEqual(parse_cli(["--fast"]), ("base-config.json", True))


if __name__ == "__main__":
    unittest.main()
