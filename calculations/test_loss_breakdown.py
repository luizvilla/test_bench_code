"""Tests for loss_breakdown.py.

Expected values come from an independent source: the cached results stored in
Nicolas's reference workbook Calculs-EssaiOct26-Manipe16Sept.xlsx (computed by
Excel, sheet "Calcul", columns G/H/I = 50/60/70 kHz), and the figures quoted in
the 13 Oct 2026 session report (17.43 mW/kHz, 3.22 W, 4.3572 uJ).

Run:  python -m pytest calculations/test_loss_breakdown.py -v
"""
import json
import os
import sys

import openpyxl
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import loss_breakdown as lb  # noqa: E402

EXCEL = os.path.join(HERE, "Calculs-EssaiOct26-Manipe16Sept.xlsx")

# Relative tolerance for per-point values: the script implements the same
# closed-form formulas as the workbook, so agreement is to float precision.
REL_TOL = 1e-9

# Excel row -> breakdown key
ROWS = {
    27: "p_in_W",
    28: "p_mos_raw_W",
    30: "p_inductor_W",
    31: "p_cap_esr_W",
    32: "p_diode_deadtime_W",
    33: "p_mos_deadtime_W",
    34: "p_mos_W",
    36: "p_remaining_W",
    37: "eoff_point_uJ",
    44: "phi_deg",
    45: "phi_time_us",
    46: "irms_eq_A",
    51: "irms_cap_A",
}


def excel_cached_values():
    ws = openpyxl.load_workbook(EXCEL, data_only=True)["Calcul"]
    return {
        ws[f"{col}7"].value: {row: ws[f"{col}{row}"].value for row in list(ROWS) + [43]}
        for col in "GHI"
    }


@pytest.fixture(scope="module")
def result():
    return lb.analyse(lb.load_reference_excel(EXCEL))


@pytest.mark.parametrize("f_khz", [50, 60, 70])
def test_per_point_breakdown_matches_excel(result, f_khz):
    expected = excel_cached_values()[f_khz]
    row = result.points[result.points["f_kHz"] == f_khz].iloc[0]
    for xl_row, key in ROWS.items():
        assert row[key] == pytest.approx(expected[xl_row], rel=REL_TOL), key


def test_fit_matches_excel_and_report(result):
    fit = result.fits[0]
    ws = openpyxl.load_workbook(EXCEL, data_only=True)["Calcul"]
    assert fit.slope_W_per_kHz == pytest.approx(ws["G39"].value, rel=REL_TOL)
    assert fit.eoff_uJ == pytest.approx(ws["G42"].value, rel=REL_TOL)
    # figures quoted in the session report, to their printed precision
    assert fit.slope_W_per_kHz * 1000 == pytest.approx(17.43, abs=0.005)
    assert fit.intercept_W == pytest.approx(3.22, abs=0.005)
    assert fit.eoff_uJ == pytest.approx(4.3572, abs=5e-5)


@pytest.mark.parametrize("f_khz", [50, 60, 70])
def test_fixed_power_matches_excel(result, f_khz):
    expected = excel_cached_values()[f_khz][43]
    row = result.points[result.points["f_kHz"] == f_khz].iloc[0]
    assert row["p_fixed_W"] == pytest.approx(expected, rel=REL_TOL)


# --------------------------------------------------------------------------- session folder


def write_session(tmp_path, inputs):
    """Write a supervisor-style session folder (ParentFolder/Experiment_name)
    whose DMM CSVs and scope results carry the given per-frequency inputs."""
    session = tmp_path / "session"
    for p in inputs:
        f = int(p["f_kHz"])
        d = session / "PhaseShift" / f"Voltage_60_{f}kHz"
        d.mkdir(parents=True)
        cfg = {"frequencyPWM": f * 1000, "DeadTimePWM": round(p["td_us"] * 1000),
               "InductorL": p["L_uH"], "nbPointsI": 1, "PhaseTab": [90]}
        (d / f"PhaseShift_Voltage_60V_Freq{f}kHz.json").write_text(json.dumps(cfg))
        (d / "csv-10_00_00-16_09_2026-Voltage.csv").write_text(json.dumps([p["vbus_V"]] * 5))
        (d / "csv-10_00_00-16_09_2026-Current.csv").write_text(json.dumps([p["i_dc_A"]] * 5))
        (d / "results.json").write_text(json.dumps({"Data1": {
            "1": {"type": "FREQ", "channel": 1, "value": f * 1000.0},
            "2": {"type": "AMPL", "channel": 2, "value": 2 * p["ipeak_A"]},
            **({} if p["irms_ind_A"] is None else
               {"3": {"type": "RMS", "channel": 2, "value": p["irms_ind_A"]}}),
        }}))
    return session


def test_session_folder_reproduces_excel_through_cli(tmp_path, capsys):
    inputs = lb.load_reference_excel(EXCEL).to_dict("records")
    session = write_session(tmp_path, inputs)
    out_csv = tmp_path / "breakdown.csv"

    assert lb.main([str(session), "-o", str(out_csv)]) == 0

    printed = capsys.readouterr().out
    assert "17.43 mW/kHz" in printed and "+ 3.220 W" in printed and "4.3572 uJ" in printed
    import pandas as pd
    got = pd.read_csv(out_csv).set_index("f_kHz")
    for f_khz, expected in excel_cached_values().items():
        assert got.loc[f_khz, "p_remaining_W"] == pytest.approx(expected[36], rel=1e-9)
        assert got.loc[f_khz, "irms_source"] == "scope"


def test_session_without_scope_rms_falls_back_to_equation(tmp_path):
    inputs = lb.load_reference_excel(EXCEL).to_dict("records")
    for p in inputs:
        p["irms_ind_A"] = None
    session = write_session(tmp_path, inputs)
    pts = lb.analyse(lb.load(str(session))).points.set_index("f_kHz")
    for f_khz, expected in excel_cached_values().items():
        assert pts.loc[f_khz, "irms_source"] == "equation"
        assert pts.loc[f_khz, "irms_used_A"] == pytest.approx(expected[46], rel=1e-9)
