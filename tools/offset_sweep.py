#!/usr/bin/env python3
"""Inductor-current DC offset vs duty correction, at a fixed phase, for a few frequencies.

Powered, automated (the supply IS driven: 0 -> Vbus ramp, current limit from the config).
For each frequency:
  1. probe zero: legs off, iL mean read on scope 1 (subtracted from every reading)
  2. SPIN set up (legs on, duty 0.5, dead time, compensation OFF, 3 deg), supply ramped to Vbus,
     phase set to the fixed point
  3. COMMON sweep: both legs at 0.5 - delta (what the firmware compensation does: td*f/2)
  4. DIFFERENTIAL sweep: leg 1 at 0.5 + Delta/2, leg 2 at 0.5 - Delta/2
  5. firmware compensation ON, one reading (reference)
  6. duty 0.5, compensation off, initial phase, ramp down, output OFF, legs off, IDLE
Each reading: iL cycle mean (CMEAN C2) and mean over >= 50 periods (MEAN C2), AMPL C2, 5 reads averaged.
A linear fit gives the Delta (and delta) that zeroes the offset; Delta*/f gives an effective dead time.
Ctrl-C: output OFF first, then the SPIN stop.

  MPLBACKEND=Agg python3 tools/offset_sweep.py                       # 50 and 100 kHz, 2 A peak, 60 V
  MPLBACKEND=Agg python3 tools/offset_sweep.py --freqs 20000 50000 --ipeak 1.5
"""

import argparse
import csv
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pyvisa as visa  # noqa: E402

from lib.SDS2104X_plus import parse_pava  # noqa: E402
from lib.TDKZ650_1_U import TDKZ650_1_U  # noqa: E402
from lib.thingset_shield import ThingSetShield  # noqa: E402

DEFAULT_CFG = os.path.join(ROOT, "sessions", "2026-11-27", "configs", "A_anchors", "PhaseShift",
                           "Voltage_60_50kHz", "PhaseShift_Voltage_60V_Freq50kHz.json")
TDIV = [1e-9, 2e-9, 5e-9, 10e-9, 20e-9, 50e-9, 100e-9, 200e-9, 500e-9, 1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6,
        100e-6, 200e-6, 500e-6, 1e-3, 2e-3, 5e-3]
MAX_DIFF = 0.005   # |Delta| cap: 1 % duty difference ~ 1.4 A of offset at 60 V / 0.42 ohm


def phase_for(ipeak, inductor_uH, freq, vbus):
    return round(360 * 2 * ipeak * inductor_uH * 1e-6 * freq / vbus, 2)


def sweep_points(span, n):
    """n points from -span to +span (n odd -> includes 0)."""
    return [round(-span + 2 * span * k / (n - 1), 5) for k in range(n)]


def fit_zero(xs, ys):
    """Least-squares line y = a x + b; returns (a, b, x where y = 0)."""
    pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
    if len(pts) < 2:
        return None, None, None
    n = len(pts); sx = sum(p[0] for p in pts); sy = sum(p[1] for p in pts)
    sxx = sum(p[0] ** 2 for p in pts); sxy = sum(p[0] * p[1] for p in pts)
    den = n * sxx - sx ** 2
    if den == 0:
        return None, None, None
    a = (n * sxy - sx * sy) / den; b = (sy - a * sx) / n
    return a, b, (-b / a if a else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=DEFAULT_CFG, help="run config (instruments, L, dead time, current limit)")
    ap.add_argument("--freqs", type=float, nargs="+", default=[50000, 100000])
    ap.add_argument("--ipeak", type=float, default=2.0, help="fixed point, A peak (default 2.0)")
    ap.add_argument("--vbus", type=float, default=60.0)
    ap.add_argument("--diff-points", type=int, default=9, help="differential sweep points (default 9)")
    ap.add_argument("--out", default=os.path.join(ROOT, "sessions", "2026-11-27", "configs", "offset_sweep"))
    ap.add_argument("--yes", action="store_true", help="do not ask before powering")
    args = ap.parse_args()

    cfg = json.load(open(args.config))
    td_s = cfg["DeadTimePWM"] * 1e-9
    initial = cfg["InitialPhaseShiftPWM"]
    out_dir = os.path.join(args.out, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out_dir)
    print(f"Offset sweep at {args.vbus:g} V, Ipeak {args.ipeak} A, dead time {cfg['DeadTimePWM']} ns, "
          f"supply limit {cfg['CurrentLimit']} A, freqs {[f / 1000 for f in args.freqs]} kHz -> {out_dir}")
    if not args.yes:
        input(">>> The supply WILL be ramped by this script. Enter to start, Ctrl-C to cancel ")

    rm = visa.ResourceManager()
    psu = TDKZ650_1_U(args.config, ressource_manager=rm)
    psu.VoltageWrite = args.vbus
    scope = rm.open_resource(cfg["AddressOSCILLO"]); scope.timeout = 5000
    shield = ThingSetShield.from_config(cfg)
    rows = []

    def cmd(*a, **k):
        return shield.sendCommand(*a, **k)

    def read(n=5):
        acc = {"CMEAN": [], "MEAN": [], "AMPL": []}
        for _ in range(n):
            for t in acc:
                v = parse_pava(scope.query(f"C2:PAVA? {t}"))
                if v is not None:
                    acc[t].append(v)
            time.sleep(0.15)
        return {t: (sum(v) / len(v) if v else None) for t, v in acc.items()}

    def scope_view(freq):
        tb = next(t for t in TDIV if t * 10 >= 50 / freq)      # >= 50 periods: MEAN bias < ~1/50 of ripple
        for c in (":ACQuire:SEQuence OFF", ":HISTORy OFF", ":MEASure OFF", f":TIMebase:SCALe {tb}", "TRDL 0",
                  ":TRIGger:EDGE:SOURce C1", ":TRIGger:EDGE:LEVel 1.0", ":TRIGger:MODE AUTO"):
            scope.write(c)
        return tb

    try:
        psu.open_hv_power_supply()
        psu.setup_hv_power_supply()                 # current limit, 0 V
        for freq in args.freqs:
            freq = int(freq)
            phase = phase_for(args.ipeak, cfg["InductorL"], freq, args.vbus)
            tb = scope_view(freq)
            cmd("IDLE"); time.sleep(1)
            zero = read()
            print(f"\n=== {freq / 1000:g} kHz, phase {phase} deg, timebase {tb * 1e6:g} us/div; "
                  f"probe zero CMEAN {zero['CMEAN']} MEAN {zero['MEAN']}")
            z = zero["MEAN"] or 0.0
            for leg in ("LEG1", "LEG2"):
                cmd("LEG", leg, "ON")
            cmd("POWER_ON")
            cmd("DUTY", "LEG1", 0.5); cmd("DUTY", "LEG2", 0.5)
            cmd("FREQUENCY", "LEG1", freq)
            for leg in ("LEG1", "LEG2"):
                cmd("DEAD_TIME_RISING", leg, cfg["DeadTimePWM"]); cmd("DEAD_TIME_FALLING", leg, cfg["DeadTimePWM"])
            cmd("DEADTIME_COMP", "OFF")
            cmd("PHASE_SHIFT", "LEG2", initial)
            psu.power_supply_output_change("ON", delay=psu.power_supply_output_delay)
            psu.power_supply_voltage_ramp_up(args.vbus, psu.voltage_step, 0, psu.power_supply_ramp_delay)
            cmd("PHASE_SHIFT", "LEG2", phase); time.sleep(1.0)

            def point(kind, d1, d2, value):
                cmd("DUTY", "LEG1", d1); cmd("DUTY", "LEG2", d2); time.sleep(0.6)
                r = read()
                row = {"f_kHz": freq / 1000, "kind": kind, "value": value, "duty1": d1, "duty2": d2,
                       "il_cmean_A": None if r["CMEAN"] is None else r["CMEAN"] - z,
                       "il_mean_A": None if r["MEAN"] is None else r["MEAN"] - z, "il_ampl_A": r["AMPL"],
                       "vbus_V": float(psu.power_supply_check_voltage(delay=0)),
                       "isupply_A": float(psu.power_supply_check_current(delay=0))}
                rows.append(row)
                print(f"  {kind:6s} {value:+.5f}: D1 {d1:.5f} D2 {d2:.5f} | iL mean {fmt(row['il_mean_A'])} "
                      f"cmean {fmt(row['il_cmean_A'])} ampl {fmt(r['AMPL'])} | Vbus {row['vbus_V']:.2f} Isup {row['isupply_A']:.3f}")
                return row

            comp = td_s * freq / 2                                   # firmware correction at this f
            for k in range(5):                                       # COMMON: 0 .. 2x the firmware value
                dlt = round(comp * k / 2, 5)
                point("common", 0.5 - dlt, 0.5 - dlt, dlt)
            for dd in sweep_points(min(MAX_DIFF, 2 * comp), args.diff_points):   # DIFFERENTIAL
                point("diff", 0.5 + dd / 2, 0.5 - dd / 2, dd)
            cmd("DUTY", "LEG1", 0.5); cmd("DUTY", "LEG2", 0.5)
            cmd("DEADTIME_COMP", "ON"); time.sleep(0.6)              # firmware compensation, reference
            r = read()
            rows.append({"f_kHz": freq / 1000, "kind": "fw_comp", "value": comp, "duty1": 0.5 - comp, "duty2": 0.5 - comp,
                         "il_cmean_A": None if r["CMEAN"] is None else r["CMEAN"] - z,
                         "il_mean_A": None if r["MEAN"] is None else r["MEAN"] - z, "il_ampl_A": r["AMPL"],
                         "vbus_V": None, "isupply_A": None})
            print(f"  fw_comp ON (D - {comp:.5f}): iL mean {fmt(rows[-1]['il_mean_A'])} cmean {fmt(rows[-1]['il_cmean_A'])}")
            cmd("DEADTIME_COMP", "OFF")
            cmd("PHASE_SHIFT", "LEG2", initial); time.sleep(0.3)
            psu.power_supply_voltage_ramp_down(args.vbus, -psu.voltage_step, -psu.voltage_step, psu.power_supply_ramp_delay)
            psu.power_set_voltage(0, delay=0.3)
            psu.power_supply_output_change("OFF")
            cmd("LEG", "LEG1", "OFF"); cmd("LEG", "LEG2", "OFF"); cmd("IDLE")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        try:
            if psu.hv_power_supply is not None:
                psu.power_set_voltage(0, delay=0.1); psu.power_supply_output_change("OFF")
        except Exception as e:
            print(f"!! supply OFF failed: {e} -- turn it off from the front panel")
        for a in (("DEADTIME_COMP", "OFF"), ("DUTY", "LEG1", 0.5), ("DUTY", "LEG2", 0.5),
                  ("PHASE_SHIFT", "LEG2", initial), ("LEG", "LEG1", "OFF"), ("LEG", "LEG2", "OFF"), ("IDLE",)):
            try:
                cmd(*a)
            except Exception:
                pass
        shield.close()
        for c in (":TIMebase:SCALe 2e-6", ":TRIGger:MODE AUTO"):
            try:
                scope.write(c)
            except Exception:
                pass
        try:
            psu.close_hv_power_supply()
        except Exception:
            pass

    if not rows:
        return
    with open(os.path.join(out_dir, "offset_sweep.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    summary = {}
    print("\n=== Fits (iL mean vs correction; zero crossing) ===")
    for freq in sorted({r["f_kHz"] for r in rows}):
        s = {}
        for kind in ("common", "diff"):
            pts = [r for r in rows if r["f_kHz"] == freq and r["kind"] == kind]
            for col in ("il_mean_A", "il_cmean_A"):
                a, b, x0 = fit_zero([p["value"] for p in pts], [p[col] for p in pts])
                s[f"{kind}_{col}"] = {"slope_A_per_duty": a, "offset_at_0_A": b, "zero_at": x0}
            m = s[f"{kind}_il_mean_A"]
            if m["slope_A_per_duty"] is not None:
                x0 = m["zero_at"]
                eff = f", effective td = {2 * x0 / (freq * 1e3) * 1e9:.0f} ns" if (kind == "common" and x0) else \
                      (f", Delta*/f = {x0 / (freq * 1e3) * 1e9:.1f} ns" if x0 else "")
                print(f"{freq:g} kHz {kind:6s}: offset at 0 = {m['offset_at_0_A']:+.3f} A, slope {m['slope_A_per_duty']:+.1f} A/duty, "
                      f"zero at {x0 if x0 is None else round(x0, 5)}{eff}")
        summary[freq] = s
    json.dump(summary, open(os.path.join(out_dir, "fits.json"), "w"), indent=2)
    print(f"Saved {out_dir}/offset_sweep.csv and fits.json")


def fmt(v):
    return "n/a" if v is None else f"{v:+.3f}"


if __name__ == "__main__":
    main()
