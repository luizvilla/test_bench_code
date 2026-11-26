"""tools/command_center.py on a synthetic session shaped like the supervisor's output."""
import json
import os
import shutil
import sys

import pytest

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "calculations"))

import command_center as cc  # noqa: E402
import loss_breakdown as lb  # noqa: E402

CONFIGS = os.path.join(REPO, "sessions", "2026-11-27", "configs")


def fill_results(d, f_khz, frames=7, samples=3, vbus=60.0):
    """Write what supervisor_script leaves in one config folder: DMM CSVs (7 plateaus),
    results.json (scope FREQ/AMPL/RMS per frame) and two screenshots per frame."""
    ipeaks = [0.5 * n for n in range(1, 8)]
    i_dc = [(3.22 + 0.01743 * f_khz + 0.35 * ip**2) / vbus for ip in ipeaks]  # September-like input power
    with open(os.path.join(d, "csv-10_00_00-27_11_2026-Voltage.csv"), "w") as fh:
        json.dump([vbus] * (7 * samples), fh)
    with open(os.path.join(d, "csv-10_00_00-27_11_2026-Current.csv"), "w") as fh:
        json.dump([i for i in i_dc for _ in range(samples)], fh)
    with open(os.path.join(d, "results.json"), "w") as fh:
        json.dump({f"Data{n}": {
            "1": {"type": "FREQ", "channel": 1, "value": f_khz * 1000.0},
            "2": {"type": "AMPL", "channel": 2, "value": 2 * ipeaks[n - 1]},
            "3": {"type": "RMS", "channel": 2, "value": ipeaks[n - 1] / 3**0.5}} for n in range(1, frames + 1)}, fh)
    for n in range(1, frames + 1):
        for name in (f"scopeData{n}.bmp", f"scope-Inverted-Data{n}.bmp"):
            open(os.path.join(d, name), "wb").close()


def make_session(root, done=None, frames=7):
    """Copy the real 27 Nov PhaseShift configs, then fill the folders listed in done {group: [f_kHz]}."""
    session = os.path.join(root, "2026-11-27")
    for group in ("A_anchors", "B_grid"):
        shutil.copytree(os.path.join(CONFIGS, group, "PhaseShift"), os.path.join(session, "configs", group, "PhaseShift"))
    done = done if done is not None else {"A_anchors": [50, 60], "B_grid": [10, 20, 30, 41, 55, 74, 100]}
    for group, freqs in done.items():
        for f in freqs:
            fill_results(os.path.join(session, "configs", group, "PhaseShift", f"Voltage_60_{f}kHz"), f, frames)
    return session


@pytest.fixture
def session(tmp_path):
    return make_session(str(tmp_path))


def test_folder_status_counts_done_and_not_run(session):
    data = cc.build_data(session, os.path.join(session, "command-center.html"))
    status = {g: {f["f_kHz"]: f["status"] for f in fs} for g, fs in data["groups"].items()}
    assert len(status["A_anchors"]) == 3 and len(status["B_grid"]) == 23
    assert status["A_anchors"] == {50: "done", 60: "done", 70: "not run"}
    assert sum(s == "done" for s in status["B_grid"].values()) == 7


def test_half_written_folder_is_partial(session):
    d = os.path.join(session, "configs", "A_anchors", "PhaseShift", "Voltage_60_70kHz")
    open(os.path.join(d, "scopeData1.bmp"), "wb").close()
    data = cc.build_data(session, os.path.join(session, "command-center.html"))
    assert {f["f_kHz"]: f["status"] for f in data["groups"]["A_anchors"]}[70] == "partial"


def test_gonogo_numbers_are_loss_breakdowns(session):
    data = cc.build_data(session, os.path.join(session, "command-center.html"))
    rows = {r["f_kHz"]: r for r in data["gonogo"]}
    assert sorted(rows) == [50.0, 60.0]  # 70 kHz has not run
    ref = lb.analyse(lb.load(os.path.join(session, "configs", "A_anchors"))).points
    ref = ref[ref["group"] == "60V_step7"].set_index("f_kHz")
    sept = {50.0: 4.0888, 60.0: 4.2719}
    for f, r in rows.items():
        assert r["p_remaining_W"] == pytest.approx(ref.loc[f, "p_remaining_W"], rel=1e-12)
        assert r["september_W"] == pytest.approx(sept[f], abs=1e-4)
        assert r["ipeak_A"] == pytest.approx(3.5) and r["ipeak_phase_A"] == pytest.approx(3.5)


def test_short_scope_sequence_is_visible(tmp_path):
    session = make_session(str(tmp_path), {"A_anchors": [50]}, frames=3)
    data = cc.build_data(session, os.path.join(session, "command-center.html"))
    f50 = data["groups"]["A_anchors"][0]
    assert (f50["frames"], f50["expected_frames"]) == (3, 7)
    row = data["gonogo"][0]
    assert row["ipeak_A"] is None or row["ipeak_A"] != row["ipeak_A"]  # no AMPL for step 7
    assert row["ipeak_phase_A"] == pytest.approx(3.5)


def test_page_is_self_contained(session):
    out = os.path.join(session, "command-center.html")
    assert cc.main([session]) == 0
    page = open(out).read()
    assert "/*__DATA__*/" not in page and "<!--__PLOTLY__-->" not in page
    assert '"session": "2026-11-27"' in page
    assert '<script src="https://cdn' not in page  # plotly embedded: works without internet


def test_nothing_run_yet_still_writes_a_page(tmp_path):
    session = make_session(str(tmp_path), {})
    data = cc.write(session, os.path.join(session, "command-center.html"))
    assert data["points"] == [] and data["gonogo"] == []


def test_resonance_bump_is_flagged_at_its_frequency_only(tmp_path):
    session = make_session(str(tmp_path), {"B_grid": [10, 14, 20, 25, 30, 41, 55, 74, 100]})
    d = os.path.join(session, "configs", "B_grid", "PhaseShift", "Voltage_60_25kHz")
    path = os.path.join(d, "csv-10_00_00-27_11_2026-Current.csv")
    with open(path) as fh:
        i_dc = json.load(fh)
    with open(path, "w") as fh:
        json.dump([i + 0.6 / 60.0 for i in i_dc], fh)  # +0.6 W at 25 kHz
    data = cc.build_data(session, os.path.join(session, "command-center.html"))
    flagged = {(p["f_kHz"], p["step"]) for p in data["points"] if p["resonance_candidate"]}
    assert flagged == {(25.0, s) for s in range(1, 8)}
