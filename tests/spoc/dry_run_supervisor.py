#!/usr/bin/env python3
"""Dry run of the real OnlyScripts supervisor on the SPOC (luizvilla/test_bench_code #10).

Runs supervisor_script.runner() on every PhaseShift config of a session group, exactly as
on the bench, except that the DMMs, the oscilloscope(s), the HV supply and VISA are stubs.
The SPIN is real: the CUT of the SPOC bench, reached through lib/thingset_shield.py. Each
command the supervisor sends is logged with its time, and any error (the runner only
collects them in a local list) is caught at the shim.

    python3 tests/spoc/dry_run_supervisor.py sessions/2026-11-27/base-config_A_anchors.json \
        --out sessions/2026-11-27/dry-run --cut-serial 5843500300470041

Results of the stubbed instruments go to a scratch folder, never next to the configs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import tempfile
import time
import traceback

os.environ.setdefault("MPLBACKEND", "Agg")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt  # noqa: E402

plt.pause = lambda *a, **k: None
plt.show = lambda *a, **k: None

import supervisor_script  # noqa: E402
from lib import thingset_shield  # noqa: E402
from lib.tools import TOOL  # noqa: E402


class Stub:
    """Stands in for an instrument: every method succeeds and does nothing."""

    def __init__(self, *a, **k):
        self.VoltageWrite = 60
        self.voltage_step = 4
        self.power_supply_ramp_delay = 0.0
        self.power_supply_output_delay = 0.0
        self.dmm_init_delay = 0.0
        self.dmm_for_current = "stub-dmm-current"
        self.dmm_for_voltage = "stub-dmm-voltage"
        self.result_output_path = None

    def dmm_get_buffer(self, *a, **k):
        return [0.0, 0.0]

    def __getattr__(self, name):
        return lambda *a, **k: None


class StubRM:
    def list_resources(self, *a, **k):
        return ()

    def close(self):
        pass


LOG: list[dict] = []
_real_send = thingset_shield.ThingSetShield.sendCommand


def logged_send(self, action, *args, delay=0.02):
    t0 = time.monotonic()
    entry = dict(t=t0, action=action, args=[a if not isinstance(a, float) else round(a, 4) for a in args])
    try:
        out = _real_send(self, action, *args, delay=delay)
        entry["ok"] = True
        return out
    except Exception as exc:
        entry["ok"] = False
        entry["error"] = str(exc)
        raise
    finally:
        entry["duration_s"] = round(time.monotonic() - t0, 3)
        LOG.append(entry)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("base_config")
    ap.add_argument("--out", default=str(ROOT / "sessions/2026-11-27/dry-run"))
    ap.add_argument("--cut-serial", default=os.environ.get("CUT_SERIAL", "5843500300470041"))
    a = ap.parse_args()

    supervisor_script.SDM3065X = Stub
    supervisor_script.SDS2104X_plus = Stub
    supervisor_script.TDKZ650_1_U = Stub
    supervisor_script.visa.ResourceManager = StubRM
    thingset_shield.ThingSetShield.sendCommand = logged_send

    base = json.load(open(a.base_config))
    group = base["Experiment_name"]
    search = ROOT / base["ParentFolder"] / group / "PhaseShift"
    configs = TOOL().find_json_files(str(search))
    scratch = pathlib.Path(tempfile.mkdtemp(prefix=f"dryrun-{group}-"))
    rows = []
    t_group = time.monotonic()
    for cfg_path in configs:
        cfg = json.load(open(cfg_path))
        cfg["dataOutputFolder"] = str(scratch / pathlib.Path(cfg_path).parent.name)
        cfg["shield_serial"] = a.cut_serial
        tmp = scratch / pathlib.Path(cfg_path).name
        tmp.write_text(json.dumps(cfg, indent=1))
        LOG.clear()
        t0 = time.monotonic()
        crash = None
        try:
            supervisor_script.runner(str(tmp))
        except Exception:
            crash = traceback.format_exc(limit=3)
        phases = [e["args"][1] for e in LOG if e["action"] == "PHASE_SHIFT"]
        sweep = [e for e in LOG if e["action"] == "PHASE_SHIFT"]
        rows.append(dict(
            config=os.path.relpath(cfg_path, ROOT), f_hz=cfg["frequencyPWM"],
            commands=len(LOG), errors=[f"{e['action']} {e['args']}: {e['error']}" for e in LOG if not e["ok"]],
            crash=crash, phases_sent=phases,
            plateau_s=round(sum(e["duration_s"] for e in sweep[:-1]) / max(1, len(sweep) - 1), 3) if sweep else None,
            run_s=round(time.monotonic() - t0, 1),
            ok=crash is None and all(e["ok"] for e in LOG) and len(phases) >= 2))
        print(f"{rows[-1]['f_hz']:>7} Hz  {len(LOG):>3} cmds  {'OK' if rows[-1]['ok'] else 'FAIL'}  {rows[-1]['run_s']} s")

    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    n_ok = sum(r["ok"] for r in rows)
    meta = dict(date=dt.datetime.now().isoformat(timespec="seconds"), group=group, base_config=a.base_config,
                cut=a.cut_serial, total_s=round(time.monotonic() - t_group, 1))
    (out / f"supervisor-{group}.json").write_text(json.dumps(dict(meta=meta, rows=rows), indent=1))
    lines = [f"# Supervisor dry run, group {group} — {meta['date']}", "",
             f"Real `supervisor_script.runner()` on {len(rows)} configs, real SPIN (SPOC CUT {a.cut_serial}) through ThingSet; "
             f"DMMs, scopes, HV supply and VISA stubbed. Group time {meta['total_s']} s.", "",
             f"**{n_ok}/{len(rows)} configs ran with every command accepted and read back.**", "",
             "| config | f (Hz) | commands | phases sent (deg) | mean plateau (s) | run (s) | result |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        res = "PASS" if r["ok"] else "**FAIL** " + "; ".join(r["errors"] + ([r["crash"].splitlines()[-1]] if r["crash"] else []))
        lines.append(f"| {r['config'].split('/')[-1]} | {r['f_hz']} | {r['commands']} | {', '.join(map(str, r['phases_sent']))} "
                     f"| {r['plateau_s']} | {r['run_s']} | {res} |")
    (out / f"supervisor-{group}.md").write_text("\n".join(lines) + "\n")
    print(f"{n_ok}/{len(rows)} PASS -> {out}/supervisor-{group}.md")
    return 0 if n_ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
