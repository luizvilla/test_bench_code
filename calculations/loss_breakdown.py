"""Loss breakdown of the test-bench H-bridge pair and P_remaining(f) fit -> Eoff.

Python port of Nicolas's workbook ``Calculs-EssaiOct26-Manipe16Sept.xlsx``
(sheet "Calcul"), so that the analysis can be re-run on any session folder.

Per operating point (Excel row in brackets):

    Ts            = 1000 / f_kHz                                   [us]   (8)
    td/Ts         = td_us / Ts                                            (16)
    P_in          = Vbus * I_dc                                           (27)
    P_mos_raw     = Rmos2 * Irms_ind^2                                    (28)
    P_inductor    = R_ind_dc * Irms_ind^2                                 (30)
    phi           = Ipeak * 4 * 180 * L_uH / (Ts * Vbus)          [deg]   (44)
    t_phi         = phi / 360 * Ts                                [us]    (45)
    Irms_cap      = Ipeak * sqrt((2 * t_phi / Ts) / 3)                    (51)
    P_cap_esr     = R_esr_cap * Irms_cap^2                                (31)
    P_diode_dt    = n_diodes * Vdiode * Ipeak * td / Ts                   (32)
    P_mos_dt      = 4 * (td/Ts) * Rmos2 * Ipeak^2                         (33)
    P_mos         = P_mos_raw - P_mos_dt   (dead-time correction)         (34)
    P_remaining   = P_in - P_inductor - P_cap_esr - P_diode_dt - P_mos    (36)
    Eoff_point    = P_remaining * Ts / 4                          [uJ]    (37)
    Irms_eq       = Ipeak * sqrt(1 - 2*phi/(3*180))  (fallback only)      (46)

Across frequencies, for each group of points sharing Vbus/Ipeak/td:

    P_remaining(f) = slope * f_kHz + intercept    (least squares, = Excel LINEST) (39)
    Eoff (1 switch) = 1000 * slope / 4            [uJ]                     (42)
    P_fixed(point)  = P_remaining - slope * f_kHz                          (43)

Inputs come from one of three sources (see ``load``):
  * the reference workbook itself (.xlsx)  -> its measured inputs, row 2..51
  * a points table (.csv) with the columns listed in INPUT_COLUMNS
  * a session folder written by the supervisor (ParentFolder/Experiment_name,
    containing PhaseShift/Voltage_<V>_<F>kHz/...), read with TraitementV10's
    CSV conversion.

CLI:  python calculations/loss_breakdown.py SOURCE [-o out.csv] [--params p.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

# Circuit parameters of the 16 Sept bench, taken from the reference workbook.
DEFAULT_CIRCUIT = {
    "r_esr_cap_ohm": 0.125,  # electrolytic cap ESR, impedance meter (13 Oct report)
    "r_ind_dc_ohm": 0.2,  # inductor DC resistance
    "r_mos2_ohm": 0.2059,  # two MOSFETs in series (conduction path)
    "v_diode_V": 0.845,  # body-diode forward voltage
    "n_diodes_deadtime": 4,  # diodes conducting during dead time
}

MEASURED_COLUMNS = [
    "group",  # points with the same group are fitted together across f
    "vbus_V",
    "i_dc_A",  # DC input current from the supply/DMM
    "ipeak_A",
    "f_kHz",
    "L_uH",
    "td_us",
    "irms_ind_A",  # inductor RMS current from the scope (NaN -> equation)
]
INPUT_COLUMNS = MEASURED_COLUMNS + list(DEFAULT_CIRCUIT)


@dataclass
class Fit:
    group: str
    n_points: int
    slope_W_per_kHz: float
    intercept_W: float
    r2: float

    @property
    def eoff_uJ(self) -> float:
        return 1000.0 * self.slope_W_per_kHz / 4.0


@dataclass
class Result:
    points: pd.DataFrame
    fits: list


# --------------------------------------------------------------------------- model


def breakdown(points: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``points`` with every loss term added as a column."""
    p = points.copy()
    for k, v in DEFAULT_CIRCUIT.items():
        if k not in p:
            p[k] = v
        p[k] = p[k].fillna(v)

    ts = 1000.0 / p["f_kHz"]
    p["Ts_us"] = ts
    p["td_over_Ts"] = p["td_us"] / ts
    p["phi_deg"] = p["ipeak_A"] * 4 * 180 * p["L_uH"] / (ts * p["vbus_V"])
    p["phi_time_us"] = p["phi_deg"] / 360 * ts
    p["irms_eq_A"] = p["ipeak_A"] * np.sqrt(1 - 2 * p["phi_deg"] / (3 * 180))
    p["irms_source"] = np.where(p["irms_ind_A"].isna(), "equation", "scope")
    irms = p["irms_ind_A"].fillna(p["irms_eq_A"])
    p["irms_used_A"] = irms
    p["irms_cap_A"] = np.sqrt((2 * p["phi_time_us"] / ts) / 3) * p["ipeak_A"]

    p["p_in_W"] = p["vbus_V"] * p["i_dc_A"]
    p["p_mos_raw_W"] = p["r_mos2_ohm"] * irms**2
    p["p_inductor_W"] = p["r_ind_dc_ohm"] * irms**2
    p["p_cap_esr_W"] = p["r_esr_cap_ohm"] * p["irms_cap_A"] ** 2
    p["p_diode_deadtime_W"] = (
        p["n_diodes_deadtime"] * p["v_diode_V"] * p["ipeak_A"] * p["td_us"] / ts
    )
    p["p_mos_deadtime_W"] = p["td_over_Ts"] * p["r_mos2_ohm"] * p["ipeak_A"] ** 2 * 4
    p["p_mos_W"] = p["p_mos_raw_W"] - p["p_mos_deadtime_W"]
    p["p_remaining_W"] = (
        p["p_in_W"]
        - p["p_inductor_W"]
        - p["p_cap_esr_W"]
        - p["p_diode_deadtime_W"]
        - p["p_mos_W"]
    )
    p["eoff_point_uJ"] = p["p_remaining_W"] * ts / 4
    return p


def fit_remaining(points: pd.DataFrame) -> list:
    """Least-squares P_remaining = slope*f_kHz + intercept, one fit per group.

    Groups with fewer than two distinct frequencies are skipped.
    """
    fits = []
    for group, g in points.groupby("group", sort=False):
        if g["f_kHz"].nunique() < 2:
            continue
        x, y = g["f_kHz"].to_numpy(float), g["p_remaining_W"].to_numpy(float)
        slope, intercept = np.polyfit(x, y, 1)
        resid = y - (slope * x + intercept)
        ss_tot = ((y - y.mean()) ** 2).sum()
        r2 = 1 - (resid**2).sum() / ss_tot if ss_tot > 0 else float("nan")
        fits.append(Fit(str(group), len(g), float(slope), float(intercept), float(r2)))
    return fits


def analyse(points: pd.DataFrame) -> Result:
    """Breakdown per point, fit per group, and P_fixed per point (Excel row 43)."""
    p = breakdown(points)
    fits = fit_remaining(p)
    slope = {f.group: f.slope_W_per_kHz for f in fits}
    p["p_switching_fit_W"] = p["group"].map(slope) * p["f_kHz"]  # row 41, 4 switches
    p["p_fixed_W"] = p["p_remaining_W"] - p["p_switching_fit_W"]
    return Result(p, fits)


# --------------------------------------------------------------------------- loaders


def load_reference_excel(path: str, sheet: str = "Calcul") -> pd.DataFrame:
    """Measured inputs of Nicolas's workbook (columns G.. of sheet 'Calcul')."""
    import openpyxl

    ws = openpyxl.load_workbook(path, data_only=True)[sheet]
    rows = []
    col = 7  # G
    while ws.cell(7, col).value is not None:
        c = lambda r: ws.cell(r, col).value  # noqa: E731
        rows.append(
            {
                "group": "excel",
                "vbus_V": c(2),
                "i_dc_A": (c(22) or 0) + (c(23) or 0),
                "ipeak_A": c(3),
                "f_kHz": c(7),
                "L_uH": c(9),
                "td_us": c(17),
                "irms_ind_A": c(48),
                "r_esr_cap_ohm": c(11),
                "r_ind_dc_ohm": c(12),
                "r_mos2_ohm": c(13),
                "v_diode_V": c(14),
                "n_diodes_deadtime": c(18),
            }
        )
        col += 1
    return pd.DataFrame(rows, columns=INPUT_COLUMNS)


def load_points_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in MEASURED_COLUMNS if c not in df and c != "irms_ind_A"]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    if "irms_ind_A" not in df:
        df["irms_ind_A"] = np.nan
    return df


def _scope_values(rdata: dict, step: int, mtype: str):
    for m in rdata.get(f"Data{step}", {}).values():
        if isinstance(m, dict) and str(m.get("type", "")).upper() == mtype:
            return m.get("value")
    return None


IPEAK_SOURCES = ("scope", "scope-pp", "phase")


def load_session_folder(
    folder: str, circuit: dict | None = None, ipeak_source: str = "scope-pp"
) -> pd.DataFrame:
    """Operating points of a supervisor session folder.

    ``folder`` is ParentFolder/Experiment_name (or its PhaseShift sub-folder).
    For each PhaseShift/Voltage_<V>_<F>kHz and each phase step:
      * Vbus, I_dc : step means of the DMM voltage/current CSVs (TraitementV10)
      * Ipeak      : ipeak_source = "scope-pp" -> scope 'AMPL' / 2 (default: AMPL is peak-to-peak, Luiz 2026-11-26)
                                    "scope"    -> scope 'AMPL' value as-is (old TraitementV10 convention)
                                    "phase"    -> Vbus*phase/180 / (4 L f) from the PhaseTab
      * Irms_ind   : scope measurement 'RMS' if present, else NaN (-> equation)
      * f, td, L   : frequencyPWM, DeadTimePWM [ns], InductorL [uH] of the PhaseShift json
    Points with the same Vbus level and step index form one fit group.
    """
    root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(root))
    from TraitementV10 import read_supervisor_series, segment_means
    from lib.phase_sweep import phase_sweep_values

    phase_dir = os.path.join(folder, "PhaseShift")
    if not os.path.isdir(phase_dir):
        phase_dir = folder
    rows = []
    for d in sorted(glob.glob(os.path.join(phase_dir, "Voltage_*_*kHz"))):
        m = re.search(r"Voltage_(\d+)_(\d+)kHz$", d)
        if not m:
            continue
        vlevel = int(m.group(1))
        cfg_files = glob.glob(os.path.join(d, "PhaseShift_*.json"))
        csv_v = [f for f in glob.glob(os.path.join(d, "*.csv")) if "-voltage" in f.lower()]
        csv_i = [f for f in glob.glob(os.path.join(d, "*.csv")) if "-current" in f.lower()]
        if not (cfg_files and csv_v and csv_i):
            print(f"[skip] {d}: missing PhaseShift json or DMM CSVs", file=sys.stderr)
            continue
        cfg = json.load(open(cfg_files[0]))
        res_file = os.path.join(d, "results.json")
        rdata = json.load(open(res_file)) if os.path.exists(res_file) else {}
        freq = cfg["frequencyPWM"]
        freq = freq[0] if isinstance(freq, list) else freq
        nb = cfg["nbPointsI"]
        means = segment_means(
            read_supervisor_series(csv_i[0]), read_supervisor_series(csv_v[0]), nb
        )
        phases = cfg.get("PhaseTab")
        if not phases:
            # The phases the supervisor actually sent (float-safe). The first one is the generator's
            # lead-in, whose measurement the OnlyScripts sweep loses: step i is sweep point i.
            sweep = phase_sweep_values(
                cfg.get("PhaseInit", 0), cfg.get("PhaseFinal", 0), cfg.get("PhaseStep", 1)
            )
            phases = sweep[1 : 1 + nb] if len(sweep) > nb else sweep
        params = {**DEFAULT_CIRCUIT, **cfg.get("LossModel", {}), **(circuit or {})}
        for i, (i_dc, v_bus) in enumerate(means, start=1):
            ampl = _scope_values(rdata, i, "AMPL")
            if ipeak_source == "phase":
                ipeak = v_bus * phases[i - 1] / 180 / (4 * cfg["InductorL"] * 1e-6 * freq)
            elif ampl is None:
                ipeak = None
            else:
                ipeak = ampl / 2 if ipeak_source == "scope-pp" else ampl
            irms = _scope_values(rdata, i, "RMS")
            rows.append(
                {
                    "group": f"{vlevel}V_step{i}",
                    "vbus_V": v_bus,
                    "i_dc_A": i_dc,
                    "ipeak_A": float("nan") if ipeak is None else ipeak,
                    "f_kHz": freq / 1000.0,
                    "L_uH": cfg["InductorL"],
                    "td_us": cfg["DeadTimePWM"] / 1000.0,
                    "irms_ind_A": float("nan") if irms is None else irms,
                    **params,
                }
            )
    if not rows:
        raise FileNotFoundError(f"no Voltage_<V>_<F>kHz session data under {folder}")
    return pd.DataFrame(rows, columns=INPUT_COLUMNS)


def load(source: str, circuit: dict | None = None, ipeak_source: str = "scope-pp") -> pd.DataFrame:
    if os.path.isdir(source):
        return load_session_folder(source, circuit, ipeak_source)
    if source.lower().endswith((".xlsx", ".xlsm")):
        df = load_reference_excel(source)
    else:
        df = load_points_csv(source)
    for k, v in (circuit or {}).items():
        df[k] = v
    return df


# --------------------------------------------------------------------------- CLI

SUMMARY_COLUMNS = [
    "group", "f_kHz", "vbus_V", "ipeak_A", "irms_used_A", "irms_source",
    "p_in_W", "p_mos_W", "p_inductor_W", "p_cap_esr_W", "p_diode_deadtime_W",
    "p_remaining_W", "p_fixed_W",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source", help="session folder, points .csv, or reference .xlsx")
    ap.add_argument("-o", "--output", help="write the full per-point breakdown to this CSV")
    ap.add_argument("--params", help="JSON file overriding circuit parameters "
                    f"({', '.join(DEFAULT_CIRCUIT)})")
    ap.add_argument("--ipeak", choices=IPEAK_SOURCES, default="scope-pp",
                    help="session folders only: where Ipeak comes from (default: scope AMPL/2, AMPL is peak-to-peak)")
    a = ap.parse_args(argv)
    circuit = json.load(open(a.params)) if a.params else None
    with np.errstate(invalid="ignore"):
        res = analyse(load(a.source, circuit, a.ipeak))

    with pd.option_context("display.width", 200, "display.max_columns", 50):
        print(res.points[SUMMARY_COLUMNS].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print()
    for f in res.fits:
        print(f"[{f.group}] P_remaining(f) = {1000 * f.slope_W_per_kHz:.2f} mW/kHz * f "
              f"+ {f.intercept_W:.3f} W  (n={f.n_points}, R2={f.r2:.4f})  "
              f"-> Eoff = {f.eoff_uJ:.4f} uJ per switch")
    if not res.fits:
        print("No fit: need >= 2 frequencies for the same group.")
    if (res.points["irms_source"] == "equation").any():
        print("WARNING: no scope RMS current for some points; Irms from the equation (row 46).")
    bad = res.points[~res.points["phi_deg"].between(0, 180)]
    if len(bad):
        print(f"WARNING: phase shift outside 0..180 deg for groups {sorted(set(bad['group']))}: "
              "check Ipeak (try --ipeak scope-pp or --ipeak phase).")
    if a.output:
        res.points.to_csv(a.output, index=False)
        print(f"breakdown written to {a.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
