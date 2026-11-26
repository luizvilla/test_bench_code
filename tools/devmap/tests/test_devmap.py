# SPDX-License-Identifier: LGPL-2.1-only
"""The dev map redrawn from a recorded tracker snapshot (snapshot.json, `devmap.py snapshot`)."""
import copy
import json
import pathlib
import sys
import tomllib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import devmap  # noqa: E402

SNAPSHOT = json.loads((HERE / "snapshot.json").read_text())
LAYOUT = tomllib.loads((HERE.parent / "layout.toml").read_text())


def snap(**changes):
    s = copy.deepcopy(SNAPSHOT)
    for key, value in changes.items():
        next(t for t in s["tickets"] if t["number"] == int(key[1:])).update(value)
    return s


def node(diagram, node_id):
    return next(l.strip() for l in diagram.splitlines() if l.strip().startswith(node_id + "["))


class Diagram(unittest.TestCase):
    def test_every_map_ticket_is_placed(self):
        self.assertNotIn("New tickets", devmap.render_diagram(SNAPSHOT, LAYOUT))

    def test_out_of_scope_nodes_are_drawn_out(self):
        d = devmap.render_diagram(SNAPSHOT, LAYOUT)
        self.assertTrue(node(d, "O1").endswith(":::out"))
        self.assertIn("classDef out", d)

    def test_out_ticket_node_shows_its_number(self):
        layout = copy.deepcopy(LAYOUT)
        layout["group"].append({"id": "X", "title": "x", "nodes": [{"id": "N14", "tickets": [14], "label": "gone", "out": True}]})
        layout["group"] = [dict(g, nodes=[n for n in g["nodes"] if n["id"] != "N14" or g["id"] == "X"]) for g in layout["group"]]
        self.assertEqual(node(devmap.render_diagram(SNAPSHOT, layout), "N14"), 'N14["#14 gone"]:::out')

    def test_closed_ticket_is_done(self):
        d = devmap.render_diagram(snap(t2={"state": "CLOSED", "assignees": []}), LAYOUT)
        self.assertTrue(node(d, "N2").startswith('N2["✓ #2'))

    def test_luiz_marker(self):
        self.assertIn("👤 #12", devmap.render_diagram(SNAPSHOT, LAYOUT))


class Project(unittest.TestCase):
    def test_no_project_means_no_changes(self):
        self.assertEqual(devmap.project_changes(SNAPSHOT, LAYOUT), [])


class Idempotent(unittest.TestCase):
    def test_redraw_twice_changes_nothing(self):
        overview = (HERE.parents[2] / "docs" / "map.md").read_text()
        body, ov, _ = devmap.plan(SNAPSHOT, LAYOUT, overview)
        s = dict(SNAPSHOT, mapBody=body)
        body2, ov2, _ = devmap.plan(s, LAYOUT, ov)
        self.assertEqual((body, ov), (body2, ov2))


if __name__ == "__main__":
    unittest.main()
