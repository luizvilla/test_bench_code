#!/usr/bin/env python3
"""One operating point, with the HV supply driven by hand from its front panel.

The script does everything the supervisor does for one current step, except the supply:
it never opens the supply, so the supply stays in LOCAL and you set voltage and current
limit yourself.

  1. SPIN set up as the supervisor does (legs on, duty, frequency, dead time, initial phase).
     Scope 1 armed for 1 frame, scope 2 armed on Vbus, both DMMs armed for 1 trigger.
  2. Pause: you raise the supply, then press Enter.
  3. One LEG2 phase write = one trigger: scope 1 frame + 30 readings per DMM.
     The phase then goes back to the initial value (low current).
  4. Pause: you lower the supply to 0 V, then press Enter.
  5. Legs off, SPIN IDLE; DMM buffers, scope 1 frame and scope 2 capture saved in the
     supervisor's folder layout, so calculations/loss_breakdown.py reads them.
Ctrl-C at any time: phase back, legs off, IDLE.

Run from the repository root, in the venv:
  MPLBACKEND=Agg python3 tools/single_point_manual.py                 # 50 kHz, 0.5 A peak, 60 V
  MPLBACKEND=Agg python3 tools/single_point_manual.py --freq 50000 --ipeak 1.0
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
from lib.SDS2104X_plus import SDS2104X_plus  # noqa: E402
from lib.thingset_shield import ThingSetShield  # noqa: E402
from lib.tools import TOOL  # noqa: E402

DEFAULT_BASE = os.path.join(ROOT, "sessions", "2026-11-27", "base-config_A_anchors.json")
DEFAULT_OUT = os.path.join(ROOT, "sessions", "2026-11-27", "configs", "single_point")


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


def scope2_window(scope, seconds):
    """Widen scope 2 so it holds a hand ramp: trigger (Vbus rising) at the left edge."""
    tb = next((t for t in scope.tdiv_enum if t * 10 >= seconds), scope.tdiv_enum[-1])
    scope.oscilloscope.write(f":TIMebase:SCALe {tb}")
    scope.oscilloscope.write(f"TRDL {-tb * 5}")
    return tb * 10


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE, help="base config (instruments, delays, L, dead time)")
    ap.add_argument("--freq", type=float, default=50000, help="switching frequency, Hz (default 50000)")
    ap.add_argument("--ipeak", type=float, default=0.5, help="peak current, A (default 0.5)")
    ap.add_argument("--vbus", type=float, default=None, help="bus voltage you will set, V (default: base Vmax)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="results folder (default: session configs/single_point)")
    ap.add_argument("--scope2-window", type=float, default=100, help="scope 2 window, s (default 100)")
    ap.add_argument("--no-scope2", action="store_true", help="do not use scope 2")
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

    print(f"\nSingle point: {freq / 1000:g} kHz, Ipeak {args.ipeak} A at {vbus:g} V -> phase {phase} deg "
          f"(initial {initial} deg), dead time {cfg['DeadTimePWM']} ns, duty {cfg['DutyPWM']}")
    print(f"Results: {run_dir}")
    print("The supply is NOT driven by this script: press REM on the supply to go to LOCAL, "
          f"set its current limit (configs: {cfg['CurrentLimit']} A) and keep it at 0 V for now.")
    input(">>> Press Enter to set up the SPIN, scopes and DMMs (Ctrl-C to cancel) ")

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
    measured = False

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

        # Arm after the initial phase write (its trigger must not be recorded), as the supervisor does
        time.sleep(0.5)
        s1.oscilloscope_setup()
        if s2:
            s2.oscilloscope_high_setup()
            window = scope2_window(s2, args.scope2_window)
            print(f"  scope 2: {window:g} s window, starts when Vbus rises through {s2.voltage_step} V")
        di.dmm_setup_current_testbench()
        dv.dmm_setup_voltage_testbench()
        armed_at = time.time()

        input(f"\n>>> Legs are switching at {initial} deg. Raise the supply to {vbus:g} V, "
              "check Vbus, then press Enter to measure ")
        wait = cfg.get("dmm_init_delay", 4) - (time.time() - armed_at)
        if wait > 0:
            print(f"  waiting {wait:.1f} s more for the DMMs to be ready")
            time.sleep(wait)

        cmd("PHASE_SHIFT", "LEG2", phase, delay=cfg.get("delay_com", 0.6))
        time.sleep(0.4)                     # a 30-sample burst takes 0.30-0.45 s
        measured = True
        cmd("PHASE_SHIFT", "LEG2", initial)  # back to low current right away
        print("  measured.")

        input(f"\n>>> Lower the supply to 0 V, then press Enter ")
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
        if measured:
            save(cfg, run_dir, s1, s2, di, dv, args.scope2_window)
        else:
            print("No measurement taken: nothing saved.")
    finally:
        for f in (lambda: s1.oscilloscope_setup_clean(), s1.close_oscilloscope,
                  (s2.close_oscilloscope if s2 else None), di.close_dmm_for_current, dv.close_dmm_for_voltage):
            if f:
                try:
                    f()
                except Exception:
                    pass


def save(cfg, run_dir, s1, s2, di, dv, window):
    tool = TOOL()
    v = dv.dmm_get_buffer(dv.dmm_for_voltage, wait_meas_complete=False)
    i = di.dmm_get_buffer(di.dmm_for_current, wait_meas_complete=False)
    tool.export_result_to_csv(str(v), "Voltage", run_dir)
    tool.export_result_to_csv(str(i), "Current", run_dir)
    s1.oscilloscope_save_results()

    if s2:
        status = s2.oscilloscope.query(":TRIGger:STATus?").strip()
        if status.lower().startswith("ready") or status.lower().startswith("arm"):
            print(f"  scope 2 never triggered (Vbus did not cross {s2.voltage_step} V): saving its screen as is")
        else:
            t0 = time.time()
            while not status.lower().startswith("stop") and time.time() - t0 < window + 5:
                print(f"  scope 2 still recording ({status}), {window + 5 - (time.time() - t0):.0f} s max ...")
                time.sleep(5)
                status = s2.oscilloscope.query(":TRIGger:STATus?").strip()
        s2.oscilloscope_save_results_high()

    mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    res = json.load(open(os.path.join(run_dir, "results.json")))
    frame = {m["type"]: m["value"] for m in res.get("Data1", {}).values()}
    vb, idc = mean(v), mean(i)
    print(f"\nDMM: {len(v)} voltage, {len(i)} current readings (30 expected each)")
    print(f"Vbus {vb:.3f} V, Idc {idc:.4f} A, Pin {vb * idc:.3f} W")
    print(f"Scope 1: {frame}  -> Ipeak = AMPL/2 = {frame.get('AMPL') / 2 if frame.get('AMPL') else 'n/a'} A")
    print(f"Saved in {run_dir}")
    print(f"Processing: python3 calculations/loss_breakdown.py {os.path.dirname(os.path.dirname(run_dir))}")


if __name__ == "__main__":
    main()
