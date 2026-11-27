#!/usr/bin/env python3
"""Inductor-current DC offset vs duty correction, at fixed phases, for a few frequencies and currents.

Powered, automated (the supply IS driven: 0 -> Vbus ramp, current limit from the config).
For each (frequency, Ipeak):
  1. probe zero: legs off, iL mean read on scope 1 (subtracted from every reading)
  2. scope 1 set up as in the campaign (supervisor channel scales sized for this Ipeak, so C2
     does not clip; timebase >= 2 periods), live AUTO on the gate C1
  3. SPIN set up (legs on, duty 0.5, dead time, compensation OFF, initial phase), supply ramped
     to Vbus, phase set to the point
  4. [unless --diff-only] COMMON sweep: both legs at 0.5 - delta (the firmware compensation's knob)
  5. DIFFERENTIAL sweep: leg 1 at 0.5 + Delta/2, leg 2 at 0.5 - Delta/2
  6. [unless --diff-only] firmware compensation ON, one reading (reference)
  7. duty 0.5, compensation off, initial phase, ramp down, output OFF, legs off, IDLE
Reading: iL cycle mean CMEAN C2 (whole periods only, the main value), MEAN C2, AMPL C2, 5 reads averaged.
A linear fit gives the Delta (and delta) that zeroes the offset.
Ctrl-C: output OFF first, then the SPIN stop.

  MPLBACKEND=Agg python3 tools/offset_sweep.py --diff-only --freqs 50000 100000 --ipeaks 0.5 3.5
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

from lib.SDS2104X_plus import SDS2104X_plus, parse_pava  # noqa: E402
from lib.TDKZ650_1_U import TDKZ650_1_U  # noqa: E402
from lib.thingset_shield import ThingSetShield  # noqa: E402

DEFAULT_CFG = os.path.join(ROOT, "sessions", "2026-11-27", "configs", "A_anchors", "PhaseShift",
                           "Voltage_60_50kHz", "PhaseShift_Voltage_60V_Freq50kHz.json")
MAX_DIFF = 0.005   # |Delta| cap: 1 % duty difference ~ 0.9 A of offset at 60 V (measured -86 A/duty)


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


def scope_imax(ipeak, diff_span):
    """Peak the C2 scale must hold: Ipeak + the largest offset the sweep can create (86 A/duty), +20 %."""
    return 1.2 * (ipeak + 86 * diff_span / 2 + 0.1)


def fmt(v):
    return "n/a" if v is None else f"{v:+.3f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=DEFAULT_CFG, help="run config (instruments, L, dead time, current limit)")
    ap.add_argument("--freqs", type=float, nargs="+", default=[50000, 100000])
    ap.add_argument("--ipeaks", type=float, nargs="+", default=[2.0], help="fixed points, A peak (default 2.0)")
    ap.add_argument("--vbus", type=float, default=60.0)
    ap.add_argument("--diff-points", type=int, default=9, help="differential sweep points (default 9)")
    ap.add_argument("--diff-values", type=float, nargs="+", default=None,
                    help="explicit Delta values instead of the sweep (e.g. 0 -0.0004 to check a trim)")
    ap.add_argument("--diff-only", action="store_true", help="differential sweep only (no common, no firmware comp)")
    ap.add_argument("--out", default=os.path.join(ROOT, "sessions", "2026-11-27", "configs", "offset_sweep"))
    ap.add_argument("--yes", action="store_true", help="do not ask before powering")
    args = ap.parse_args()

    cfg = json.load(open(args.config))
    td_s = cfg["DeadTimePWM"] * 1e-9
    base_initial = cfg["InitialPhaseShiftPWM"]
    out_dir = os.path.join(args.out, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out_dir)
    points = [(int(f), ip) for f in args.freqs for ip in args.ipeaks]
    for f, ip in points:
        ph = phase_for(ip, cfg["InductorL"], f, args.vbus)
        if not 0 < ph <= cfg.get("Limited_PHI", 175):
            sys.exit(f"{f / 1000:g} kHz, {ip} A -> phase {ph} deg out of range")
    print(f"Offset sweep at {args.vbus:g} V, dead time {cfg['DeadTimePWM']} ns, supply limit {cfg['CurrentLimit']} A, "
          f"{'differential only' if args.diff_only else 'common + differential'}: "
          + ", ".join(f"{f / 1000:g} kHz/{ip} A" for f, ip in points) + f" -> {out_dir}")
    if not args.yes:
        input(">>> The supply WILL be ramped by this script. Enter to start, Ctrl-C to cancel ")

    rm = visa.ResourceManager()
    psu = TDKZ650_1_U(args.config, ressource_manager=rm)
    psu.VoltageWrite = args.vbus
    sc = SDS2104X_plus(args.config, ressource_manager=rm, address=cfg["AddressOSCILLO"])
    shield = ThingSetShield.from_config(cfg)
    rows = []

    def cmd(*a, **k):
        return shield.sendCommand(*a, **k)

    def read(n=5):
        acc = {"CMEAN": [], "MEAN": [], "AMPL": []}
        for _ in range(n):
            for t in acc:
                v = parse_pava(sc.oscilloscope.query(f"C2:PAVA? {t}"))
                if v is not None:
                    acc[t].append(v)
            time.sleep(0.15)
        return {t: (sum(v) / len(v) if v else None) for t, v in acc.items()}

    def scope_view(freq, imax):
        sc.frequencyPWM = freq
        sc.imax = imax
        sc.oscilloscope_setup()          # campaign scales (C2 sized from imax) and >= 2-period timebase
        sc.free_run()
        o = sc.oscilloscope
        o.write(":TRIGger:EDGE:SOURce C1"); o.write(":TRIGger:EDGE:LEVel 1.0"); o.write(":TRIGger:MODE AUTO")
        return float(o.query(":TIMebase:SCALe?")), float(o.query(":CHANnel2:SCALe?"))

    try:
        sc.open_oscilloscope()
        psu.open_hv_power_supply()
        psu.setup_hv_power_supply()                 # current limit, 0 V
        for freq, ipeak in points:
            phase = phase_for(ipeak, cfg["InductorL"], freq, args.vbus)
            initial = min(base_initial, round(phase / 2, 2))
            comp = td_s * freq / 2                                    # firmware correction at this f
            diff_span = min(MAX_DIFF, 2 * comp)
            tb, vdiv = scope_view(freq, scope_imax(ipeak, diff_span))
            cmd("IDLE"); time.sleep(1)
            zero = read()
            z = zero["CMEAN"] if zero["CMEAN"] is not None else (zero["MEAN"] or 0.0)
            print(f"\n=== {freq / 1000:g} kHz, {ipeak} A peak, phase {phase} deg; scope {tb * 1e6:g} us/div "
                  f"({tb * 10 * freq:.1f} periods), C2 {vdiv:g} A/div; probe zero {z:+.4f} A")
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

            def record(kind, value, d1, d2, r, with_supply=True):
                row = {"f_kHz": freq / 1000, "ipeak_A": ipeak, "phase_deg": phase, "kind": kind, "value": value,
                       "duty1": d1, "duty2": d2,
                       "il_cmean_A": None if r["CMEAN"] is None else r["CMEAN"] - z,
                       "il_mean_A": None if r["MEAN"] is None else r["MEAN"] - z, "il_ampl_A": r["AMPL"],
                       "vbus_V": float(psu.power_supply_check_voltage(delay=0)) if with_supply else None,
                       "isupply_A": float(psu.power_supply_check_current(delay=0)) if with_supply else None}
                rows.append(row)
                print(f"  {kind:7s} {value:+.5f}: D1 {d1:.5f} D2 {d2:.5f} | iL cmean {fmt(row['il_cmean_A'])} "
                      f"mean {fmt(row['il_mean_A'])} ampl {fmt(r['AMPL'])}"
                      + (f" | Vbus {row['vbus_V']:.2f} Isup {row['isupply_A']:.3f}" if with_supply else ""))

            def point(kind, d1, d2, value):
                cmd("DUTY", "LEG1", d1); cmd("DUTY", "LEG2", d2); time.sleep(0.6)
                record(kind, value, d1, d2, read())

            if not args.diff_only:
                for k in range(5):                                   # COMMON: 0 .. 2x the firmware value
                    dlt = round(comp * k / 2, 5)
                    point("common", 0.5 - dlt, 0.5 - dlt, dlt)
            for dd in (args.diff_values or sweep_points(diff_span, args.diff_points)):   # DIFFERENTIAL
                point("diff", 0.5 + dd / 2, 0.5 - dd / 2, dd)
            cmd("DUTY", "LEG1", 0.5); cmd("DUTY", "LEG2", 0.5)
            if not args.diff_only:
                cmd("DEADTIME_COMP", "ON"); time.sleep(0.6)          # firmware compensation, reference
                record("fw_comp", comp, 0.5 - comp, 0.5 - comp, read(), with_supply=False)
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
                  ("PHASE_SHIFT", "LEG2", base_initial), ("LEG", "LEG1", "OFF"), ("LEG", "LEG2", "OFF"), ("IDLE",)):
            try:
                cmd(*a)
            except Exception:
                pass
        shield.close()
        for f in (sc.free_run, sc.close_oscilloscope, psu.close_hv_power_supply):
            try:
                f()
            except Exception:
                pass

    if not rows:
        return
    with open(os.path.join(out_dir, "offset_sweep.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    summary = {}
    print("\n=== Fits (iL cycle mean vs correction; zero crossing) ===")
    for freq, ipeak in sorted({(r["f_kHz"], r["ipeak_A"]) for r in rows}):
        s = {}
        for kind in ("common", "diff"):
            pts = [r for r in rows if r["f_kHz"] == freq and r["ipeak_A"] == ipeak and r["kind"] == kind]
            if not pts:
                continue
            for col in ("il_cmean_A", "il_mean_A"):
                a, b, x0 = fit_zero([p["value"] for p in pts], [p[col] for p in pts])
                s[f"{kind}_{col}"] = {"slope_A_per_duty": a, "offset_at_0_A": b, "zero_at": x0}
            m = s[f"{kind}_il_cmean_A"]
            at0 = next((p["il_cmean_A"] for p in pts if p["value"] == 0), None)
            if m["slope_A_per_duty"] is not None:
                print(f"{freq:g} kHz {ipeak} A {kind:6s}: offset measured at 0 = {fmt(at0)} A, fit {m['offset_at_0_A']:+.3f} A, "
                      f"slope {m['slope_A_per_duty']:+.1f} A/duty, zero at {None if m['zero_at'] is None else round(m['zero_at'], 5)}")
        summary[f"{freq:g}kHz_{ipeak}A"] = s
    json.dump(summary, open(os.path.join(out_dir, "fits.json"), "w"), indent=2)
    print(f"Saved {out_dir}/offset_sweep.csv and fits.json")


if __name__ == "__main__":
    main()
