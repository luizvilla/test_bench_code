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
