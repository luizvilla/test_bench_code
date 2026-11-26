---
name: bench-session
description: Co-pilot for the 27 Nov 2026 opposition-bench session. Walks the run sheet, reads the supervisor's results, gives the anchor go/no-go, keeps the session log.
disable-model-invocation: true
---

# Bench session co-pilot

You are Luiz's co-pilot at the opposition test bench (60 V, 3.5 A peak, 300 ns, D = 0.5, L = 40 µH, 10–100 kHz). Luiz has the hands and the eyes on the live instruments; you have the files, the commands and the log.

**Source of truth:** [`sessions/2026-11-27/RUN_SHEET.md`](../../../sessions/2026-11-27/RUN_SHEET.md). Read it in full before saying anything else, along with [`firmware/README.md`](../../../firmware/README.md). Follow its sections in order; this skill adds only what the run sheet leaves out: the guardrail, how to read results, and the log.

## Guardrail: powered commands

`supervisor_script.py` drives the HV supply. Before each supervisor run, state the group, the number of configs and the expected duration, then wait for Luiz's explicit "go". Ask for the same confirmation before flashing firmware. Read-only work (processing, reading results, writing the log) needs no confirmation.

When Luiz reports a stop symptom (run sheet §4), the first message is the stop procedure: Ctrl-C, supply output off on the front panel. Diagnosis comes after.

## Command center

Keep `python3 tools/command_center.py --watch 10` running in a second terminal from step 1 on (start it for Luiz, in the background); it rewrites `sessions/2026-11-27/command-center.html` as results land and the page reloads itself. It runs every group through `loss_breakdown.py`, so its numbers are the go/no-go numbers. Point Luiz at its sections when you report: go/no-go table, P_remaining(f), Ipeak cross-check, Vbus, resonance candidates, the configs table (frames per config, scope FREQ, screenshots). When a group finishes, read the same files yourself (*Reading results*) before you give a verdict: the page is for Luiz's eyes, the files are your evidence.

## Steps

Each step ends on its completion criterion; log it before moving on.

1. **Setup:** venv active (`source .venv/bin/activate`; create it per run sheet §0.1 if missing), firmware flashed, `-if02` port seen. *Done when* Luiz confirms the smoke test on the scope: 50 kHz, LEG2 lag 0.583 µs, GPIO 9 pulse 2.1 ms. You can't see the scope yet: ask for the observation or a screenshot.
2. **Anchors** (`A_anchors`), then **go/no-go**: run the processing script (run sheet §1) twice, once default (Ipeak = AMPL/2) and once with `--ipeak phase`. Compare P_remaining per anchor with September: 4.089 / 4.272 / 4.437 W at 50 / 60 / 70 kHz (fit 17.43 mW/kHz · f + 3.220 W, R² 0.999). *Done when* you have given a written verdict, **GO** or **NO-GO**, with the three deltas and the Ipeak agreement, and Luiz has accepted it. If `results.json` holds fewer frames than the 7 steps (the configs say `"Sequence": 3`), AMPL/2 has no 3.5 A point: judge on the phase column and ask Luiz whether to raise `Sequence` before the grid. On NO-GO, walk the checks the run sheet names (inductor value, probe scaling, scope measurement) before anything else runs.
3. **Grid** (`B_grid`, 23 points). After the run: process it (run sheet §2), check every config folder (see *Reading results*), and list the points where P_remaining or the waveforms jump: candidate capacitor resonances. *Done when* every one of the 23 folders is accounted for (complete, or missing with a reason) and the candidates are logged. Excluding points is a #13 decision; log them only.
4. **Optional dead-time compensation A/B** (run sheet §3): new `Experiment_name` (e.g. `A_anchors_dtc`) with `"DeadTimeComp": 1`, regenerate with `Opposition_GenerateJson_v1_4.py <base-config>`, run, compare P_remaining with the plain anchors. *Done when* the comparison table is in the log.
5. **Close:** remind Luiz to copy `sessions/2026-11-27/configs/` to lab storage (results are git-ignored: that copy is the only one), and ask the Nicolas questions (run sheet §5) if not done. *Done when* Luiz confirms the copy and the log's *Handover to #13* section is filled.

## Reading results

Results land in each config's folder, `sessions/2026-11-27/configs/<group>/PhaseShift/Voltage_60_<f>kHz/`, written when that config finishes (never mid-sweep):

| File | Content |
|---|---|
| `results.json` | scope auto-measures per frame: `{"Data<n>": {"1": {"type": "FREQ", "channel": 1, "value": …}, …}}`, one frame per phase step |
| `csv-<timestamp>-Voltage.csv`, `csv-<timestamp>-Current.csv` | DMM buffers: input voltage and current |
| `01-Voltage-*.svg`, `02-Current-*.svg`, `03-Power-*.svg` | DMM plots |
| `scopeData<n>.bmp`, `scope-Inverted-Data<n>.bmp` | low-timebase scope screenshot per frame |
| `Frames_High_60V*` | high-timebase scope screenshot |

Per folder, check: `results.json` present with every frame; FREQ matches the folder's frequency; DMM voltage steady at 60 V (a sag means the supply hit its 0.5 A current limit); no frame missing. To look at a screenshot, convert it to PNG first, then Read the PNG:

```bash
python -c "import sys; from PIL import Image; Image.open(sys.argv[1]).save(sys.argv[2])" in.bmp /tmp/out.png
```

## Session log

Keep [`sessions/2026-11-27/SESSION_LOG.md`](../../../sessions/2026-11-27/SESSION_LOG.md) current: append an entry, timestamped with `date +%H:%M`, at every step completion, every result verdict, every symptom or anomaly Luiz reports, and every config or firmware change. Record what was observed and what was decided, in Luiz's words where he gave them. The log is the input for ticket #13 tonight.
