# Run sheet — Open-Power session, 27 November 2026

Goal of the session (report of 13 Oct): consolidate experimental data between 10 and 100 kHz and confront it with the loss-breakdown Excel. Operating point: **60 V, 3.5 A peak (7 current points 0.5–3.5 A), 300 ns dead time, D = 0.5, L = 40 µH**. Map: [luizvilla/test_bench_code#1](https://github.com/luizvilla/test_bench_code/issues/1).

Everything below runs from the root of branch `session-2026-11-27`.

## 0. Before powering anything (≈ 20 min)

1. **Code:** `git fetch && git checkout session-2026-11-27 && git pull`; `pip install -r requirements.txt` (pyserial is needed for ThingSet).
2. **Flash the bench SPIN** with `firmware/bench-thingset-554f8b9a.mcuboot.bin` (ThingSet, fractional phase, 10 kHz minimum). Either OwnTech's *Firmware flasher* widget on the console port as before, or with the core checked out at `554f8b9a`: `pio run -e USB -t upload`. Details and the ST-Link variant: [`firmware/README.md`](../../firmware/README.md).
3. **Check the board answers:** it enumerates as `OwnTech Technologies TWIST_V1_4_2` with two ports. `ls -l /dev/serial/by-id/` → the ThingSet one ends in `-if02`. If more than one SPIN is plugged in, put its serial in **both** base configs and the generated configs as `"shield_serial"` (or its path as `"shield_port"`); otherwise the supervisor refuses to guess.
4. **Smoke test without HV:** `python3 -c "from lib.thingset_shield import ThingSetShield as T; s=T.open(); print(s.sendCommand('FREQUENCY','LEG1',50000), s.sendCommand('PHASE_SHIFT','LEG2',10.5))"` and look at the gate signals on the scope: 50 kHz, LEG2 lagging 0.583 µs, GPIO 9 (pin PC7) pulsing 2.1 ms after the phase write.
5. **Scope:** channel 2 = inductor current; the configs ask for `FREQ` ch1, `AMPL` ch2 (peak-to-peak) and `RMS` ch2. The trigger input on GPIO 9 as before.
6. **Supply:** `CurrentLimit` is 0.5 A in the configs (was 0.3 A).

## 1. Anchors first: 50, 60, 70 kHz (≈ 10 min)

```bash
python3 supervisor_script.py sessions/2026-11-27/base-config_A_anchors.json
python3 calculations/loss_breakdown.py sessions/2026-11-27/configs/A_anchors
```

**Check before going on:** P_remaining(f) of the anchors against September (17.43 mW/kHz · f + 3.22 W, R² 0.999). Ipeak is read as AMPL/2; `--ipeak phase` is the cross-check. If they disagree by more than the scatter of September, stop and look (inductor value, probe scaling, scope measurement) before spending the session on the grid.

## 2. Grid: 23 points 10–100 kHz (≈ 45–60 min)

```bash
python3 supervisor_script.py sessions/2026-11-27/base-config_B_grid.json
python3 calculations/loss_breakdown.py sessions/2026-11-27/configs/B_grid -o sessions/2026-11-27/B_grid_breakdown.csv
```

- Points below 30 kHz have small phases (2.4–45°): fine with this firmware (±0.05°), flagged in the README table.
- Watch for the **capacitor resonance** (electrolytic, 125 mΩ ESR): note the frequencies where the waveforms or P_remaining jump; they are excluded later, not now.

## 3. Optional: dead-time duty compensation A/B on the anchors

The compensation is in the flashed firmware (D − td·f/2 on both legs, ticket #8). Copy the anchors group under a new `Experiment_name` (e.g. `A_anchors_dtc`) with `"DeadTimeComp": 1`, run it, and compare the mean of iL on the scope and P_remaining with the plain anchors.

## 4. If the new firmware misbehaves

- **Symptoms that mean "stop":** a write refused (the supervisor log shows `ThingSetShieldError`), the scope trigger missing, gate signals not matching the commanded phase.
- **Fallback:** the string-protocol firmware `owntech/spin_code_compiled.mcuboot.bin` (branch `ReleaseCandidate`) with `"shield_protocol": "string"` and `"shield_pid": 257` in the configs. **Limits of the fallback:** whole degrees only (fractional phases are truncated), and **no frequency below 50 kHz** (the old firmware keeps the Twist's 50 kHz minimum): only the anchors and the grid points ≥ 55 kHz can run.
- **Stopping mid-run:** Ctrl-C, then the supply output off from its front panel if the script did not get to it; the SPIN stops its legs on `IDLE` / `POWER_OFF` (checked on the SPOC: no truncated pulse on stop).

## 5. Questions for Nicolas (from the processing script)

See [`calculations/README.md`](../../calculations/README.md), "Open questions on the model": the 4·(td/Ts)·Ipeak² dead-time term, what "I DC condo" is, RMS vs cycle RMS, the fit grouping. Also: access to the LAPLACE share for the 16 September raw data (ticket #15).

## 6. After the session

- Results are git-ignored next to the configs: **copy `sessions/2026-11-27/configs/` to the lab storage** before leaving.
- Then ticket #13 *Record the 27 November session results*: run the processing script on both groups, write the session report, note excluded points and why.

## Verified tonight (SPOC bench, no power stage)

- [Firmware check](dry-run/firmware-check.md): 269/270 (frequency on the 26 points, 183 phase points within ±4 ns, dead time, dead-time compensation, GPIO 9 pulse, phase steps, stops). The one FAIL is a capture artefact at 10 kHz, compensation OFF, on PA8; the hand measurement in the report shows the firmware is right.
- Supervisor dry run: 26/26 configs (real `supervisor_script` on every config, instruments stubbed, real SPIN): see `dry-run/supervisor-*.md`.
