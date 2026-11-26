#!/usr/bin/env python3
"""Command center of a bench session: one self-contained HTML page with every result and interactive plots.

Usage (repository root, in the venv):
    python3 tools/command_center.py [SESSION_DIR] [--out FILE] [--watch SECONDS]

SESSION_DIR defaults to sessions/2026-11-27. Reads what supervisor_script.py writes,
SESSION_DIR/configs/<group>/PhaseShift/Voltage_<V>_<F>kHz/ (config json, DMM CSVs, results.json,
scope screenshots), runs each group through calculations/loss_breakdown.py (the model lives
there only) and writes SESSION_DIR/command-center.html. Plotly is embedded: the page needs no
internet. --watch regenerates whenever a results file changes; the page then reloads itself.
Changes nothing but the output page.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import glob
import html
import io
import json
import math
import os
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "calculations"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import loss_breakdown as lb  # noqa: E402
from TraitementV10 import read_supervisor_series  # noqa: E402

EXCEL = os.path.join(REPO, "calculations", "Calculs-EssaiOct26-Manipe16Sept.xlsx")
DEFAULT_SESSION = os.path.join(REPO, "sessions", "2026-11-27")
RESONANCE_SIGMAS = 3.0  # a point further than this many robust sigmas from its step's fit is a candidate
RESONANCE_FLOOR_W = 0.02  # ... and further than this: below it, noise at the low-current steps
e = html.escape


# --------------------------------------------------------------------------- scanning


def _finite(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else x


def scan_folder(d: str, out_dir: str) -> dict:
    """What one config folder holds. status: 'done' (results.json + both DMM CSVs), 'partial', 'not run'."""
    m = re.search(r"Voltage_(\d+)_(\d+)kHz$", d)
    cfg_files = glob.glob(os.path.join(d, "PhaseShift_*.json"))
    cfg = json.load(open(cfg_files[0])) if cfg_files else {}
    csvs = glob.glob(os.path.join(d, "*.csv"))
    csv_v = [f for f in csvs if "-voltage" in f.lower()]
    csv_i = [f for f in csvs if "-current" in f.lower()]
    res_file = os.path.join(d, "results.json")
    results = json.load(open(res_file)) if os.path.exists(res_file) else None
    shots = sorted(glob.glob(os.path.join(d, "scope*.bmp")) + glob.glob(os.path.join(d, "Frames_High*")))
    produced = [p for p in [res_file] + csv_v + csv_i + shots if os.path.exists(p)]
    if results is not None and csv_v and csv_i:
        status = "done"
    elif produced:
        status = "partial"
    else:
        status = "not run"
    freqs = []
    for frame in (results or {}).values():
        for meas in frame.values():
            if isinstance(meas, dict) and str(meas.get("type", "")).upper() == "FREQ":
                freqs.append(_finite(meas.get("value")))
    dmm = {}
    for key, files in (("V", csv_v), ("I", csv_i)):
        try:
            dmm[key] = [float(x) for x in read_supervisor_series(files[0])] if files else []
        except Exception as exc:  # a half-written CSV must not take the page down
            dmm[key] = []
            dmm[key + "_error"] = str(exc)
    return {
        "dir": d,
        "name": os.path.basename(d),
        "f_kHz": int(m.group(2)) if m else None,
        "vlevel": int(m.group(1)) if m else None,
        "status": status,
        "frames": len(results or {}),
        "expected_frames": cfg.get("nbPointsI"),
        "scope_freq_Hz": freqs,
        "dmm": dmm,
        "shots": [os.path.relpath(s, out_dir) for s in shots],
        "dead_time_comp": int(cfg.get("DeadTimeComp", 0) or 0),
        "updated": max((os.path.getmtime(p) for p in produced), default=None),
    }


def scan_session(session: str, out_dir: str) -> dict:
    """{group: [folder, ...] sorted by f} for every configs/<group>/PhaseShift."""
    groups = {}
    for phase_dir in sorted(glob.glob(os.path.join(session, "configs", "*", "PhaseShift"))):
        folders = [scan_folder(d, out_dir) for d in glob.glob(os.path.join(phase_dir, "Voltage_*_*kHz"))]
        groups[os.path.basename(os.path.dirname(phase_dir))] = sorted(folders, key=lambda f: f["f_kHz"] or 0)
    return groups


# --------------------------------------------------------------------------- analysis


def _step(group_label: str) -> int:
    m = re.search(r"step(\d+)$", str(group_label))
    return int(m.group(1)) if m else 0


def load_group(session: str, group: str) -> tuple:
    """(inputs scope-pp, inputs phase) of one group, or (None, None) when nothing ran yet."""
    folder = os.path.join(session, "configs", group)
    try:
        with contextlib.redirect_stderr(io.StringIO()):  # the loader names every folder not run yet
            return lb.load(folder, ipeak_source="scope-pp"), lb.load(folder, ipeak_source="phase")
    except FileNotFoundError:
        return None, None


def resonance_flags(points: pd.DataFrame) -> pd.Series:
    """True where P_remaining sits off its step's line: residual > max(RESONANCE_SIGMAS robust sigmas,
    RESONANCE_FLOOR_W) against a fit redone without the outliers (a bump must not drag the line to itself)."""
    flags = pd.Series(False, index=points.index)
    for _, g in points.dropna(subset=["p_remaining_W"]).groupby("group"):
        if len(g) < 5:
            continue
        x, y = g["f_kHz"].to_numpy(float), g["p_remaining_W"].to_numpy(float)
        inl = np.ones(len(x), bool)
        for _ in range(3):
            coef = np.polyfit(x[inl], y[inl], 1)
            resid = y - np.polyval(coef, x)
            sigma = 1.4826 * np.median(np.abs(resid[inl] - np.median(resid[inl])))
            new = np.abs(resid) <= max(RESONANCE_SIGMAS * sigma, RESONANCE_FLOOR_W)
            if new.sum() < 3 or (new == inl).all():
                break
            inl = new
        flags.loc[g.index] = ~inl
    return flags


def build_data(session: str, out_file: str) -> dict:
    """Everything the page shows, as plain JSON-able data."""
    out_dir = os.path.dirname(os.path.abspath(out_file))
    groups = scan_session(session, out_dir)
    sept = lb.analyse(lb.load(EXCEL))
    sept_fit = sept.fits[0]

    per_group, plain_pp, plain_ph, errors = {}, [], [], {}
    for group, folders in groups.items():
        try:
            pp, ph = load_group(session, group)
        except Exception as exc:
            errors[group] = f"{type(exc).__name__}: {exc}"
            continue
        if pp is None:
            continue
        pp, ph = pp.assign(run=group), ph.assign(run=group)
        per_group[group] = (pp, ph)
        if not any(f["dead_time_comp"] for f in folders):
            plain_pp.append(pp)
            plain_ph.append(ph)

    points, fits = [], []
    if plain_pp:
        res = lb.analyse(pd.concat(plain_pp, ignore_index=True))
        res_ph = lb.analyse(pd.concat(plain_ph, ignore_index=True))
        p = res.points
        p["ipeak_phase_A"] = res_ph.points["ipeak_A"].to_numpy()
        p["p_remaining_phase_W"] = res_ph.points["p_remaining_W"].to_numpy()
        p["step"] = p["group"].map(_step)
        p["resonance_candidate"] = resonance_flags(p)
        points = json.loads(p.to_json(orient="records", double_precision=15))
        fits = [{"group": f.group, "step": _step(f.group), "slope_W_per_kHz": f.slope_W_per_kHz,
                 "intercept_W": f.intercept_W, "r2": f.r2, "eoff_uJ": f.eoff_uJ, "n": f.n_points}
                for f in res.fits]

    top = max((pt["step"] for pt in points), default=0)
    sept_pts = {round(r["f_kHz"]): r["p_remaining_W"] for r in sept.points.to_dict("records")}
    gonogo = []
    for pt in points:
        if pt["step"] == top and round(pt["f_kHz"]) in sept_pts:
            ref = sept_pts[round(pt["f_kHz"])]
            gonogo.append({"run": pt["run"], "f_kHz": pt["f_kHz"], "september_W": ref,
                           "p_remaining_W": pt["p_remaining_W"], "p_remaining_phase_W": pt["p_remaining_phase_W"],
                           "ipeak_A": pt["ipeak_A"], "ipeak_phase_A": pt["ipeak_phase_A"],
                           "delta_W": None if pt["p_remaining_W"] is None else pt["p_remaining_W"] - ref,
                           "delta_phase_W": None if pt["p_remaining_phase_W"] is None else pt["p_remaining_phase_W"] - ref})

    dtc = []
    comp = {g: v for g, v in per_group.items() if any(f["dead_time_comp"] for f in groups[g])}
    if comp and points:
        plain_top = {round(pt["f_kHz"]): pt for pt in points if pt["step"] == top}
        for g, (pp, _) in comp.items():
            cp = lb.analyse(pp).points
            for r in cp[cp["group"].map(_step) == top].to_dict("records"):
                base = plain_top.get(round(r["f_kHz"]))
                dtc.append({"run": g, "f_kHz": r["f_kHz"], "p_remaining_on_W": _finite(r["p_remaining_W"]),
                            "p_remaining_off_W": base["p_remaining_W"] if base else None})

    return {
        "session": os.path.basename(os.path.normpath(session)),
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "groups": {g: [{k: v for k, v in f.items() if k != "dir"} for f in fs] for g, fs in groups.items()},
        "errors": errors,
        "points": points,
        "fits": fits,
        "top_step": top,
        "september": {"points": json.loads(sept.points[["f_kHz", "p_remaining_W", "ipeak_A"]].to_json(orient="records")),
                      "slope_W_per_kHz": sept_fit.slope_W_per_kHz, "intercept_W": sept_fit.intercept_W,
                      "r2": sept_fit.r2, "eoff_uJ": sept_fit.eoff_uJ},
        "gonogo": gonogo,
        "dtc": dtc,
    }


# --------------------------------------------------------------------------- page


def plotly_js() -> str:
    try:
        from plotly.offline import get_plotlyjs
        return "<script>" + get_plotlyjs() + "</script>"
    except ImportError:  # no plotly in this Python: fall back to the CDN (needs internet)
        print("[warn] plotly not installed (pip install -r requirements.txt): the page loads it from the CDN",
              file=sys.stderr)
        return '<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>'


def render(data: dict, watch: int | None = None) -> str:
    template = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "command_center.html")).read()
    payload = json.dumps(data, allow_nan=False, default=str).replace("</", "<\\/")
    return (template.replace("/*__DATA__*/null", payload)
            .replace("/*__WATCH__*/0", str(int(watch or 0)))
            .replace("<!--__PLOTLY__-->", plotly_js())
            .replace("__TITLE__", e(f"Command center {data['session']}")))


def _clean(obj):
    """NaN/inf -> None, recursively, so the page gets valid JSON."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def write(session: str, out_file: str, watch: int | None = None) -> dict:
    data = _clean(build_data(session, out_file))
    tmp = out_file + ".tmp"
    with open(tmp, "w") as f:
        f.write(render(data, watch))
    os.replace(tmp, out_file)  # the browser never reloads a half-written page
    return data


def _signature(session: str) -> tuple:
    files = glob.glob(os.path.join(session, "configs", "*", "PhaseShift", "Voltage_*", "*"))
    return tuple(sorted((f, os.path.getmtime(f)) for f in files if os.path.isfile(f)))


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("session", nargs="?", default=DEFAULT_SESSION)
    a.add_argument("--out", help="output HTML (default SESSION/command-center.html)")
    a.add_argument("--watch", type=int, metavar="SECONDS", help="regenerate when results change, checking every SECONDS")
    args = a.parse_args(argv)
    out = args.out or os.path.join(args.session, "command-center.html")
    sig = None
    while True:
        new = _signature(args.session)
        if new != sig:
            data = write(args.session, out, args.watch)
            done = sum(f["status"] == "done" for fs in data["groups"].values() for f in fs)
            total = sum(len(fs) for fs in data["groups"].values())
            print(f"[{data['generated']}] {out}: {done}/{total} configs done", flush=True)
            sig = new
        if not args.watch:
            return 0
        time.sleep(args.watch)


if __name__ == "__main__":
    sys.exit(main())
