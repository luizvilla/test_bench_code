#!/usr/bin/env python3
"""One operating point, with the HV supply driven by hand from its front panel.

The script never opens the supply: it stays in LOCAL and you set voltage and current limit.
Every step waits for Enter, and scope 1 stays live (AUTO, triggered on the gate C1) the whole
time, so you watch the phase step happen without any reset of the screen.

  1. SPIN set up as the supervisor does (legs on, duty, frequency, dead time, initial phase).
     DMMs armed on a software trigger (2 bursts of 30 readings). Scopes live.
  2. You raise the supply, then Enter.
  3. BEFORE: one DMM burst + live scope reading at the initial phase.
  4. Enter: phase step to the asked Ipeak. DURING: one DMM burst + live scope readings.
     The phase is held until you press Enter.
  5. Enter: phase back to the initial value. You lower the supply, then Enter.
  6. Legs off, SPIN IDLE. Saved in the supervisor's folder layout (the DURING burst and
     scope values are what calculations/loss_breakdown.py reads; BEFORE is saved beside).
Ctrl-C at any time: phase back, legs off, IDLE.

Run from the repository root, in the venv:
  MPLBACKEND=Agg python3 tools/single_point_manual.py                 # 50 kHz, 0.5 A peak, 60 V
  MPLBACKEND=Agg python3 tools/single_point_manual.py --ipeak 1.0
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pyvisa as visa  # noqa: E402

from lib.SDM3065X import SDM3065X  # noqa: E402
from lib.SDS2104X_plus import SDS2104X_plus, parse_pava  # noqa: E402
from lib.thingset_shield import ThingSetShield  # noqa: E402
from lib.tools import TOOL  # noqa: E402

DEFAULT_BASE = os.path.join(ROOT, "sessions", "2026-11-27", "base-config_A_anchors.json")
DEFAULT_OUT = os.path.join(ROOT, "sessions", "2026-11-27", "configs", "single_point")
BURST_S = 0.6      # a 30-sample burst takes 0.30-0.45 s
SCOPE_READS = 5    # live scope readings averaged per state


def phase_for(ipeak, inductor_uH, freq, vbus):
    """Phase (deg) for a peak current, same formula as Opposition_GenerateJson: dI = 2 Ipeak."""
    return round(360 * 2 * ipeak * inductor_uH * 1e-6 * freq / vbus, 2)


def point_config(base, freq, ipeak, vbus, phase, run_dir):
    cfg = dict(base)
    cfg.update(
        frequencyPWM=freq, nbPointsI=1, nbPointsV=1, Imin=ipeak, Imax=ipeak,
        Vmin=vbus, Vmax=vbus, VoltageWrite=vbus,
        PhaseInit=phase, PhaseFinal=phase, PhaseStep=1.0,
        dataOutputFolder=run_dir, SupplyMode="manual (front panel)",
    )
    cfg.pop("Sequence", None)
    return cfg


def live_view(scope, measures):
    """Scope 1 live: supervisor channel scales and >= 2-period timebase, trigger AUTO on the gate
    (C1 rising) so the waveform is stable and never frozen, and the measurements of the config
    shown on screen without statistics."""
    scope.oscilloscope_setup()          # scales, timebase (arms segmented memory...)
    scope.free_run()                    # ...which free_run undoes: sequence off, AUTO
    o = scope.oscilloscope
    o.write(":TRIGger:EDGE:SOURce C1")
    o.write(":TRIGger:EDGE:LEVel 1.0")
    o.write(":TRIGger:MODE AUTO")
    scope.ConfigMeasure()               # panel on, advanced mode
    for i, m in enumerate(measures):
        scope.NewMeasure(i + 1, m)
    o.write(":MEASure:ADVanced:STATistics OFF")


def read_scope(scope, measures, n=SCOPE_READS):
    """Average of n live readings per measure (None if the scope never had a value)."""
    out = {}
    for i, m in enumerate(measures):
        vals = []
        for _ in range(n):
            v = parse_pava(scope.oscilloscope.query(f"C{m['channel']}:PAVA? {m['type']}"))
            if v is not None:
                vals.append(v)
            time.sleep(0.1)
        out[str(i + 1)] = {"type": m["type"], "channel": m["channel"],
                           "value": sum(vals) / len(vals) if vals else None}
    return out


def dmm_arm_software(dmm, bursts):
    """Same setup as the testbench (range, NPLC, 30 samples), but triggered by *TRG."""
    dmm.write("ABORt")
    dmm.write("TRIG:SOUR BUS")
    dmm.write(f"TRIG:COUN {bursts}")
    dmm.write("INITiate")


def burst(dmms):
    for d in dmms:
        d.write("*TRG")
    time.sleep(BURST_S)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE, help="base config (instruments, delays, L, dead time)")
    ap.add_argument("--freq", type=float, default=50000, help="switching frequency, Hz (default 50000)")
    ap.add_argument("--ipeak", type=float, default=0.5, help="peak current, A (default 0.5)")
    ap.add_argument("--vbus", type=float, default=None, help="bus voltage you will set, V (default: base Vmax)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="results folder (default: session configs/single_point)")
    ap.add_argument("--no-scope2", action="store_true", help="no scope 2 screenshot")
    args = ap.parse_args()

    base = json.load(open(args.base))
    vbus = args.vbus or base["Vmax"]
    freq = int(args.freq)
    phase = phase_for(args.ipeak, base["InductorL"], freq, vbus)
    if not 0 <= phase <= base.get("Limited_PHI", 175):
        sys.exit(f"phase {phase} deg out of 0..{base.get('Limited_PHI', 175)}: lower --ipeak or raise --vbus")
    initial = base["InitialPhaseShiftPWM"]

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(os.path.abspath(args.out), stamp, "PhaseShift", f"Voltage_{int(vbus)}_{freq // 1000}kHz")
    os.makedirs(run_dir)
    cfg = point_config(base, freq, args.ipeak, vbus, phase, run_dir)
    # PhaseShift_* so loss_breakdown finds it; not PhaseShift_Voltage_* (those configs are git-tracked)
    cfg_path = os.path.join(run_dir, f"PhaseShift_SinglePoint_{int(vbus)}V_Freq{freq // 1000}kHz.json")
    json.dump(cfg, open(cfg_path, "w"), indent=4)
    measures = cfg["ScopeAutoMeasure"]

    print(f"\nSingle point: {freq / 1000:g} kHz, Ipeak {args.ipeak} A at {vbus:g} V -> phase {phase} deg "
          f"(initial {initial} deg), dead time {cfg['DeadTimePWM']} ns, duty {cfg['DutyPWM']}")
    print(f"Results: {run_dir}")
    print("The supply is NOT driven by this script: press REM on the supply to go to LOCAL, "
          f"set its current limit (configs: {cfg['CurrentLimit']} A) and keep it at 0 V for now.")
    input(">>> Enter: set up the SPIN, scopes and DMMs (Ctrl-C to cancel) ")

    rm = visa.ResourceManager()
    s1 = SDS2104X_plus(cfg_path, ressource_manager=rm, address=cfg["AddressOSCILLO"])
    s2 = None if args.no_scope2 or not cfg.get("AddressOSCILLOhigh") else \
        SDS2104X_plus(cfg_path, ressource_manager=rm, address=cfg["AddressOSCILLOhigh"])
    di = SDM3065X("current", cfg_path, ressource_manager=rm)
    dv = SDM3065X("voltage", cfg_path, ressource_manager=rm)
    for s in (s1, s2):
        if s:
            s.result_output_path = run_dir
    shield = None
    scope_before = scope_during = None
    t_step = None

    def cmd(*a, **k):
        r = shield.sendCommand(*a, **k)
        print(f"  SPIN {a} -> {r}")
        return r

    try:
        di.open_dmm_for_current()
        dv.open_dmm_for_voltage()
        shield = ThingSetShield.from_config(cfg)
        s1.open_oscilloscope()
        if s2:
            s2.open_oscilloscope()

        # SPIN exactly as Supervisor.microcontroller_setup
        cmd("LEG", "LEG1", "ON")
        cmd("LEG", "LEG2", "ON")
        cmd("POWER_ON")
        cmd("DUTY", "LEG1", cfg["DutyPWM"])
        cmd("DUTY", "LEG2", cfg["DutyPWM"])
        cmd("FREQUENCY", "LEG1", freq)
        for leg in ("LEG2", "LEG1"):
            cmd("DEAD_TIME_RISING", leg, cfg["DeadTimePWM"])
        for leg in ("LEG2", "LEG1"):
            cmd("DEAD_TIME_FALLING", leg, cfg["DeadTimePWM"])
        if cfg.get("DeadTimeComp") is not None:
            cmd("DEADTIME_COMP", "ON" if cfg["DeadTimeComp"] else "OFF")
        cmd("PHASE_SHIFT", "LEG2", initial)

        live_view(s1, measures)
        if s2:
            s2.free_run()
        di.dmm_setup_current_testbench()
        dv.dmm_setup_voltage_testbench()
        dmms = (dv.dmm_for_voltage, di.dmm_for_current)
        for d in dmms:
            dmm_arm_software(d, bursts=2)
        armed_at = time.time()

        input(f"\n>>> Legs switching at {initial} deg, scopes live. Raise the supply to {vbus:g} V, "
              "check Vbus, then Enter ")
        wait = cfg.get("dmm_init_delay", 4) - (time.time() - armed_at)
        if wait > 0:
            print(f"  waiting {wait:.1f} s more for the DMMs to be ready")
            time.sleep(wait)
        burst(dmms)                                    # BEFORE, at the initial phase
        scope_before = read_scope(s1, measures)
        print(f"  BEFORE ({initial} deg): scope {fmt(scope_before)}")

        input(f"\n>>> Enter: phase step {initial} -> {phase} deg (watch scope 1) ")
        cmd("PHASE_SHIFT", "LEG2", phase)
        t_step = time.time()
        time.sleep(cfg.get("delay_com", 0.6))         # settle, as the supervisor's plateau
        burst(dmms)                                    # DURING, at the measurement phase
        scope_during = read_scope(s1, measures)
        print(f"  DURING ({phase} deg): scope {fmt(scope_during)}")

        input(f"\n>>> Holding {phase} deg. Enter: back to {initial} deg ")
        print(f"  held {time.time() - t_step:.1f} s")
        cmd("PHASE_SHIFT", "LEG2", initial)

        input(f"\n>>> Lower the supply to 0 V, then Enter ")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        if shield is not None:
            for a in (("PHASE_SHIFT", "LEG2", initial), ("LEG", "LEG1", "OFF"), ("LEG", "LEG2", "OFF"), ("IDLE",)):
                try:
                    cmd(*a)
                except Exception as e:  # keep stopping
                    print(f"  SPIN {a} failed: {e}")
            shield.close()

    try:
        if scope_during is not None:
            save(run_dir, s2, di, dv, scope_before, scope_during, initial, phase)
        else:
            print("No measurement taken during the step: nothing saved.")
    finally:
        for f in (s1.oscilloscope_setup_clean, (s2.free_run if s2 else None), s1.close_oscilloscope,
                  (s2.close_oscilloscope if s2 else None), di.close_dmm_for_current, dv.close_dmm_for_voltage):
            if f:
                try:
                    f()
                except Exception:
                    pass


def fmt(meas):
    return ", ".join(f"{m['type']} C{m['channel']} {m['value']:.4g}" if m["value"] is not None
                     else f"{m['type']} C{m['channel']} n/a" for m in meas.values())


def save(run_dir, s2, di, dv, scope_before, scope_during, initial, phase):
    tool = TOOL()
    v = dv.dmm_get_buffer(dv.dmm_for_voltage, wait_meas_complete=False)
    i = di.dmm_get_buffer(di.dmm_for_current, wait_meas_complete=False)
    v_before, v_during, i_before, i_during = v[:30], v[30:], i[:30], i[30:]
    # DURING is the measurement point (what loss_breakdown reads: '-Voltage'/'-Current', Data1)
    tool.export_result_to_csv(str(v_during), "Voltage", run_dir)
    tool.export_result_to_csv(str(i_during), "Current", run_dir)
    tool.export_result_to_csv(str(v_before), "BeforeStepV", run_dir)
    tool.export_result_to_csv(str(i_before), "BeforeStepI", run_dir)
    json.dump({"Data1": scope_during, "BeforeStep": scope_before}, open(os.path.join(run_dir, "results.json"), "w"), indent=4)
    if s2:
        s2.oscilloscope_save_picture("SinglePoint_High")   # live screen of scope 2, for the record

    mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    print(f"\nDMM readings: voltage {len(v_before)} + {len(v_during)}, current {len(i_before)} + {len(i_during)} (30 + 30 expected)")
    for label, vv, ii, sc, ph in (("BEFORE", v_before, i_before, scope_before, initial), ("DURING", v_during, i_during, scope_during, phase)):
        vb, idc = mean(vv), mean(ii)
        ampl = next((m["value"] for m in sc.values() if m["type"] == "AMPL"), None)
        print(f"{label} {ph:>6} deg: Vbus {vb:.3f} V, Idc {idc:.4f} A, Pin {vb * idc:.3f} W, "
              f"Ipeak = AMPL/2 = {ampl / 2 if ampl else float('nan'):.3f} A")
    print(f"Saved in {run_dir}")
    print(f"Processing: python3 calculations/loss_breakdown.py {os.path.dirname(os.path.dirname(run_dir))}")


if __name__ == "__main__":
    main()
