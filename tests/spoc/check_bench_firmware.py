#!/usr/bin/env python3
"""SPOC check of the ThingSet bench firmware (luizvilla/test_bench_code #3, #4, #7, #10).

The Spin under test (CUT) runs the bench firmware (luizvilla/Core power_tuesday-v2);
nothing is powered: the MUX Spin routes CUT pins to the Rigol MHO984 and the checks
read the scope's own waveforms. Commands go through lib/thingset_shield.py, the same
path the supervisor uses.

    python3 tests/spoc/check_bench_firmware.py --out sessions/2026-11-27/dry-run

Pins (Twist 1.4.2 on the Spin): LEG1 high = PA8, LEG2 high = PB12, LEG2 low = PB13,
scope trigger GPIO 9 = PC7. The SPOC has two wires (Core2 docs/safety/spoc_bench.md):
TP1-TP3 joins CH1 and CH2, TP5-TP7 joins CH3 and CH4. So only two channels are
independent: never route two CUT outputs into the same pair (they would fight
through the mux). This script uses CH1 and CH3 only, and Bench.route() refuses
anything else.
Only queries from the MHO900 programming guide are sent (an unknown one hangs the link).
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORE2_COMMON = pathlib.Path(os.environ.get("CORE2_TESTS_COMMON", "/home/luiz-villa/code/Core2/tests/common"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CORE2_COMMON))

import rigol_mho  # noqa: E402  (Core2 tests/common: the SPOC scope driver)
from spoc.mux_controller import MuxController  # noqa: E402
from spoc import boards  # noqa: E402
from lib.thingset_shield import ThingSetShield  # noqa: E402
from lib.phase_sweep import phase_sweep_values  # noqa: E402  (the supervisor's own sweep)

THRESHOLD_V = 1.65          # 3.3 V logic
CONTROL_PERIOD_S = 100e-6   # bench firmware critical task
TRIGGER_PERIODS = 21        # GPIO 9 high for 21 control periods
TOL_FREQ = 0.005            # relative
TOL_PHASE_S = 4e-9          # edge vs commanded phase: one timer tick (~2.9 ns with the 10 kHz minimum) + 1 ns; trigger jitter alone spans about +-2.5 ns (90 kHz, 129.6 deg: -2.6..+1.6 ns over 4 captures)
TOL_DEAD_S = 15e-9
TOL_WIDTH_S = 0.5e-6        # glitch scan: pulse/gap width vs nominal


# ------------------------------------------------------------------ helpers

def crossings(t, v, slope):
    out = []
    for i in range(1, len(v)):
        a, b = v[i - 1], v[i]
        if (slope > 0 and a < THRESHOLD_V <= b) or (slope < 0 and a >= THRESHOLD_V > b):
            out.append(t[i - 1] + (THRESHOLD_V - a) * (t[i] - t[i - 1]) / (b - a))
    return out


class Bench:
    def __init__(self, cut_serial: str | None):
        self.shield = ThingSetShield.open(serial_number=cut_serial)
        mux_port = boards.find("mux")
        if not mux_port:
            raise SystemExit("MUX Spin not found (run Core2 tests/common/spoc_preflight.sh)")
        self.mux = MuxController(mux_port)
        self.mux.connect()
        self.scope = rigol_mho.RigolScope(rigol_mho.open_transport())
        for ch in (1, 3, 4):
            self.scope.setup_channel(ch, scale=1, offset=-1.65, probe=10)

    def cmd(self, *a):
        return self.shield.sendCommand(*a)

    SHARED_NODES = ({"ch1", "ch2"}, {"ch3", "ch4"})

    def route(self, routes: dict[str, str]):
        for node in self.SHARED_NODES:
            if len(node & set(routes)) > 1:
                raise ValueError(f"{sorted(node & set(routes))} share one SPOC node: route one CUT pin per pair")
        self.mux.disable_all()
        items = list(routes.items())
        self.mux.route(*items[0])           # route() disables every other route first
        for ch, pin in items[1:]:
            self.mux.route_fast(ch, pin)     # no "previous": that argument names a route to turn OFF
        for ch, pin in items:
            if not self.mux.read_route(ch, pin).enabled:
                raise RuntimeError(f"MUX route {pin} -> {ch} not enabled")

    def configure(self, f_hz, duty=0.5, dead_ns=300, phase=0.0):
        for c in [("IDLE",), ("FREQUENCY", "LEG1", int(f_hz)),
                  ("DUTY", "LEG1", duty), ("DUTY", "LEG2", duty),
                  ("DEAD_TIME_RISING", "LEG1", dead_ns), ("DEAD_TIME_FALLING", "LEG1", dead_ns),
                  ("DEAD_TIME_RISING", "LEG2", dead_ns), ("DEAD_TIME_FALLING", "LEG2", dead_ns),
                  ("PHASE_SHIFT", "LEG2", float(phase)),
                  ("LEG", "LEG1", "ON"), ("LEG", "LEG2", "ON"), ("POWER_ON",)]:
            self.cmd(*c)
        time.sleep(0.05)

    def edge_near(self, trig_ch, trig_slope, ch, slope, expected_s, window_s):
        """Time (after the trigger edge) of the `slope` edge of `ch` nearest `expected_s`."""
        sc = self.scope
        sc.set_timebase(window_s / 10, expected_s)
        sc.set_edge_trigger(trig_ch, THRESHOLD_V, "POSitive" if trig_slope > 0 else "NEGative", sweep="NORMal")
        for _ in range(3):                    # an empty record now and then: retry
            self.fresh(window_s / 10)
            t, v = sc.waveform(ch)
            xs = crossings(t, v, slope)
            if xs:
                return min(xs, key=lambda x: abs(x - expected_s))
        return None

    def fresh(self, scale_s):
        """A fresh record: run, wait for several triggers, stop (single() can return a stale
        record on the MHO984)."""
        self.scope.run()
        time.sleep(0.6 + 30 * scale_s)
        self.scope.write(":STOP")
        time.sleep(0.15)

    def capture(self, chans, scale_s, offset_s, trig_ch, action=None, settle_s=0.3):
        """Run the scope (normal sweep), do `action`, stop on the last trigger, read waveforms."""
        sc = self.scope
        sc.set_timebase(scale_s, offset_s)
        sc.set_edge_trigger(trig_ch, THRESHOLD_V, "POSitive", sweep="NORMal")
        sc.run()
        time.sleep(0.2 + 12 * scale_s)
        if action:
            action()
        time.sleep(settle_s + 12 * scale_s)
        sc.write(":STOP")
        time.sleep(0.05)
        return {ch: sc.waveform(ch) for ch in chans}


# ------------------------------------------------------------------ checks

def session_points():
    """(frequency, [phases]) of the 2026-11-27 PhaseShift configs, anchors first."""
    pts = []
    for group in ("A_anchors", "B_grid"):
        files = glob.glob(str(ROOT / f"sessions/2026-11-27/configs/{group}/PhaseShift/*/*.json"))
        for p in sorted(files, key=lambda p: json.load(open(p))["frequencyPWM"]):
            d = json.load(open(p))
            phases = [float(x) for x in phase_sweep_values(d["PhaseInit"], d["PhaseFinal"], d["PhaseStep"])]
            pts.append((group, int(d["frequencyPWM"]), phases))
    return pts


def check_frequency_and_phase(b: Bench, results: list, points):
    b.route({"ch1": "PA8", "ch3": "PB12"})
    for group, f, phases in points:
        T = 1.0 / f
        b.configure(f)
        b.scope.set_timebase(2 * T / 10, 0)
        b.scope.set_edge_trigger(1, THRESHOLD_V, sweep="AUTO")
        b.scope.run()
        time.sleep(0.8)
        meas = b.scope.measure("FREQuency", 1)
        ok = meas is not None and abs(meas - f) / f <= TOL_FREQ
        results.append(dict(check="frequency", group=group, f_hz=f, expected=f, measured=meas, ok=ok))
        targets = sorted({p for p in phases if p > 0} | ({10.5} if f == 10000 else set()))
        for ph in targets:
            b.cmd("PHASE_SHIFT", "LEG2", ph)
            time.sleep(0.05)
            exp = ph / 360.0 * T
            got = b.edge_near(1, +1, 3, +1, exp, 200e-9)
            err = None if got is None else got - exp
            results.append(dict(check="phase", group=group, f_hz=f, phase_deg=ph, expected_ns=exp * 1e9,
                                measured_ns=None if got is None else got * 1e9,
                                error_ns=None if err is None else err * 1e9,
                                error_deg=None if err is None else err / T * 360,
                                ok=err is not None and abs(err) <= TOL_PHASE_S))


def check_dead_time(b: Bench, results: list, freqs):
    b.route({"ch1": "PB12", "ch3": "PB13"})
    for f in freqs:
        b.configure(f)
        for name, trig, tgt in (("H fall -> L rise", 1, 3), ("L fall -> H rise", 3, 1)):
            got = b.edge_near(trig, -1, tgt, +1, 300e-9, 1e-6)
            results.append(dict(check="dead time", f_hz=f, edge=name, expected_ns=300.0,
                                measured_ns=None if got is None else got * 1e9,
                                ok=got is not None and abs(got - 300e-9) <= TOL_DEAD_S))


def check_trigger_pulse(b: Bench, results: list):
    b.route({"ch3": "PC7"})
    b.configure(50000, phase=10.0)
    w = b.capture([3], 500e-6, 2e-3, 3, action=lambda: b.cmd("PHASE_SHIFT", "LEG2", 20.0))
    t, v = w[3]
    r, f = crossings(t, v, +1), crossings(t, v, -1)
    width = (min(x for x in f if x > r[0]) - r[0]) if r and any(x > r[0] for x in f) else None
    lo, hi = (TRIGGER_PERIODS - 1) * CONTROL_PERIOD_S, (TRIGGER_PERIODS + 2) * CONTROL_PERIOD_S  # one period of jitter on the set
    results.append(dict(check="GPIO 9 trigger pulse", expected=f"{lo*1e3:.1f}-{hi*1e3:.1f} ms",
                        measured_ms=None if width is None else width * 1e3,
                        ok=width is not None and lo <= width <= hi))


def pulse_widths(t, v):
    r, f = crossings(t, v, +1), crossings(t, v, -1)
    highs = [min(x for x in f if x > a) - a for a in r if any(x > a for x in f)]
    lows = [min(x for x in r if x > a) - a for a in f if any(x > a for x in r)]
    return highs, lows


def check_phase_steps(b: Bench, results: list, f, phases, duty=0.5, dead_s=300e-9):
    """#4: phase steps on LEG2 (down to 0, then up) leave no runt, no skipped period and no
    stretched pulse beyond what the step itself implies.

    Moving a periodic signal by dphi means exactly one period at the transition is longer
    or shorter by dphi/360*T: the scan allows at most one high and one low time off
    nominal, and only by that amount (within the capture's resolution). The capture is
    triggered by the GPIO 9 pulse of each write. LEG1 is not watched (two independent
    channels on the SPOC)."""
    b.route({"ch1": "PB12", "ch3": "PC7"})
    T = 1.0 / f
    start = max(phases)
    b.configure(f, phase=start)
    hi_nom, lo_nom = duty * T - dead_s, (1 - duty) * T + dead_s
    seq = sorted(phases, reverse=True)[1:] + [0.0] + sorted(phases)
    scale = max(20e-6, 2 * T / 10 * 2)
    step_res = 10 * scale / 1000              # screen record: 1000 points
    tol = TOL_WIDTH_S + 2 * step_res
    prev = start
    for ph in seq:
        w = b.capture([1], scale, -3 * scale, 3, action=lambda ph=ph: b.cmd("PHASE_SHIFT", "LEG2", ph))
        dt_step = abs(ph - prev) / 360.0 * T
        highs, lows = pulse_widths(*w[1])
        bad, notes = [], []
        if len(highs) < 2:
            bad.append(f"only {len(highs)} complete pulse(s) in the window")
        for kind, widths, nom in (("high", highs, hi_nom), ("low", lows, lo_nom)):
            off = [x for x in widths if abs(x - nom) > tol]
            if len(off) > 1:
                bad.append(f"{len(off)} {kind} times off nominal: " + ", ".join(f"{x*1e6:.2f} us" for x in off))
            for x in off[:1]:
                d = abs(x - nom)
                if abs(d - dt_step) > tol:
                    bad.append(f"{kind} {x*1e6:.2f} us: off by {d*1e6:.2f} us, step implies {dt_step*1e6:.2f} us")
                else:
                    notes.append(f"{kind} {x*1e6:.2f} us (step {dt_step*1e6:.2f} us)")
        results.append(dict(check="phase step glitch scan", f_hz=f, from_deg=prev, to_deg=ph,
                            transition="; ".join(notes) or "-", anomalies="; ".join(bad) or "none", ok=not bad))
        prev = ph


def check_stop(b: Bench, results: list, f, n=10, duty=0.5, dead_s=300e-9, stop=("POWER_OFF",)):
    """#4, stop: the last high pulse of each leg before POWER_OFF is complete (not cut short).

    The scope holds the last falling edge of the watched leg (normal sweep), i.e. the end of
    the final pulse; a stop in the middle of a pulse shows as a short last pulse."""
    import random
    T = 1.0 / f
    hi_nom = duty * T - dead_s
    scale = 3 * T / 10
    for leg, pin in (("LEG2", "PB12"), ("LEG1", "PA8")):
        b.route({"ch1": pin})
        short = []
        for i in range(n):
            b.configure(f, phase=round(random.uniform(0, 170), 2))
            sc = b.scope
            sc.set_timebase(scale, -4 * scale)
            sc.set_edge_trigger(1, THRESHOLD_V, "NEGative", sweep="NORMal")
            sc.run()
            time.sleep(0.3 + 30 * scale)
            b.cmd(*stop)
            time.sleep(0.4)
            sc.write(":STOP")
            time.sleep(0.15)
            highs, _ = pulse_widths(*sc.waveform(1))
            last = highs[-1] if highs else None
            if last is None or last < hi_nom - TOL_WIDTH_S:
                short.append(None if last is None else round(last * 1e6, 3))
        results.append(dict(check="stop: last pulse complete", f_hz=f, leg=leg, stop=" ".join(stop), stops=n,
                            truncated="none" if not short else f"{len(short)}: {short} us",
                            ok=not short))


# ------------------------------------------------------------------ report

def write_report(out: pathlib.Path, results: list, meta: dict):
    out.mkdir(parents=True, exist_ok=True)
    (out / "firmware-check.json").write_text(json.dumps(dict(meta=meta, results=results), indent=1))
    n_ok = sum(r["ok"] for r in results)
    lines = [f"# SPOC check of the ThingSet bench firmware — {meta['date']}", "",
             f"Core `{meta['core']}`, CUT {meta['cut']}, scope {meta['scope']}.",
             f"**{n_ok}/{len(results)} PASS.** Tolerances: frequency ±{TOL_FREQ*100:.1f} %, phase edge ±{TOL_PHASE_S*1e9:.0f} ns, "
             f"dead time ±{TOL_DEAD_S*1e9:.0f} ns, glitch scan ±{TOL_WIDTH_S*1e6:.1f} µs.", ""]
    by = {}
    for r in results:
        by.setdefault(r["check"], []).append(r)
    for check, rows in by.items():
        keys = [k for k in rows[0] if k not in ("check",)]
        lines += [f"## {check} ({sum(r['ok'] for r in rows)}/{len(rows)} PASS)", "",
                  "| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
        for r in rows:
            cells = []
            for k in keys:
                x = r.get(k)
                cells.append(("PASS" if x else "**FAIL**") if k == "ok" else (f"{x:.3f}" if isinstance(x, float) else str(x)))
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    (out / "firmware-check.md").write_text("\n".join(lines))
    return n_ok, len(results)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "sessions/2026-11-27/dry-run"))
    ap.add_argument("--cut-serial", default=os.environ.get("CUT_SERIAL", "5843500300470041"))
    ap.add_argument("--core", default=os.environ.get("BENCH_CORE", "unknown"))
    ap.add_argument("--quick", action="store_true", help="3 frequencies instead of the whole grid")
    a = ap.parse_args()
    b = Bench(a.cut_serial)
    pts = session_points()
    if a.quick:
        pts = [p for p in pts if p[1] in (10000, 50000, 100000)]
    results = []
    check_trigger_pulse(b, results)
    check_frequency_and_phase(b, results, pts)
    check_dead_time(b, results, [10000, 50000, 100000])
    for f in (10000, 50000):
        phases = next(p[2] for p in pts if p[1] == f)
        check_phase_steps(b, results, f, [x for x in phases if x > 0])
    for f in (10000, 50000):
        check_stop(b, results, f)
        check_stop(b, results, f, stop=("LEG", "LEG2", "OFF"))
    b.cmd("IDLE")
    b.mux.disable_all()
    meta = dict(date=dt.datetime.now().isoformat(timespec="seconds"), core=a.core, cut=a.cut_serial,
                scope=b.scope.idn().strip())
    n_ok, n = write_report(pathlib.Path(a.out), results, meta)
    print(f"{n_ok}/{n} PASS -> {a.out}/firmware-check.md")
    return 0 if n_ok == n else 1


if __name__ == "__main__":
    sys.exit(main())
