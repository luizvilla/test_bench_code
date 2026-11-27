"""Run from the repository root: python -m unittest discover -s tests

The scope records one segmented frame per current step, so its frame count
comes from nbPointsI. The legacy "Sequence" key (3 in the old base config while
7 currents were swept) must not cut the steps above it.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lib.SDS2104X_plus import SDS2104X_plus  # noqa: E402


def scope_from(config):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(config, f)
    try:
        # any non-None resource manager: the constructor does not open the scope
        return SDS2104X_plus(f.name, ressource_manager=object())
    finally:
        os.unlink(f.name)


class ScopeFrameCountTest(unittest.TestCase):
    def test_one_frame_per_current_step(self):
        self.assertEqual(scope_from({"nbPointsI": 7}).Sequence, 7)

    def test_legacy_sequence_key_does_not_override(self):
        self.assertEqual(scope_from({"nbPointsI": 7, "Sequence": 3}).Sequence, 7)


if __name__ == "__main__":
    unittest.main()
