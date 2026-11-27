# Run sheet — Open-Power session, 27 November 2026

Goal of the session (report of 13 Oct): consolidate experimental data between 10 and 100 kHz and confront it with the loss-breakdown Excel. Operating point: **60 V, 3.5 A peak (7 current points 0.5–3.5 A), 300 ns dead time, D = 0.5, L = 40 µH**. Map: [luizvilla/test_bench_code#1](https://github.com/luizvilla/test_bench_code/issues/1).

Everything below runs from the root of branch `session-2026-11-27`.

## 0. Before powering anything (≈ 20 min)

1. **Code:** `git fetch && git checkout session-2026-11-27 && git pull`; `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` (pyserial is needed for ThingSet). **Every command below runs in this venv**: the system pandas breaks against a newer numpy in `~/.local` (`numpy.dtype size changed`).
2. **Flash the bench SPIN** with `firmware/bench-thingset-554f8b9a.mcuboot.bin` (ThingSet, fractional phase, 10 kHz minimum). Either OwnTech's *Firmware flasher* widget on the console port as before, or with the core checked out at `554f8b9a`: `pio run -e USB -t upload`. Details and the ST-Link variant: [`firmware/README.md`](../../firmware/README.md).
3. **Check the board answers:** it enumerates as `OwnTech Technologies TWIST_V1_4_2` with two ports. `ls -l /dev/serial/by-id/` → the ThingSet one ends in `-if02`. If more than one SPIN is plugged in, put its serial in **both** base configs and the generated configs as `"shield_serial"` (or its path as `"shield_port"`); otherwise the supervisor refuses to guess.
4. **Smoke test without HV:** `python3 -c "from lib.thingset_shield import ThingSetShield as T; s=T.open(); print(s.sendCommand('FREQUENCY','LEG1',50000), s.sendCommand('PHASE_SHIFT','LEG2',10.5))"` and look at the gate signals on the scope: 50 kHz, LEG2 lagging 0.583 µs, GPIO 9 (pin PC7) pulsing 2.1 ms after the phase write.
5. **Scope:** channel 2 = inductor current; the configs ask for `FREQ` ch1, `AMPL` ch2 (peak-to-peak) and `RMS` ch2. The trigger input on GPIO 9 as before.
6. **Supply:** `CurrentLimit` is 0.2 A in the configs (27 Nov, was 0.5 A; the 50 kHz anchor peaks at Pin 7.8 W = 0.13 A at 60 V, Vbus sag 0.15 V, no CC). Check it is on USB: `ls -l /dev/serial/by-id/` must list `usb-TDK-Lambda_Z+_Serial_Port_…`. If it is missing and `journalctl -k | grep "usb 3-"` shows `error -71` / `unable to enumerate USB device`, **power-cycle the supply with the USB cable plugged in** (seen on 27 Nov: re-plugging and remote mode did not help, the power cycle did). Then check it answers `*IDN?` before running the supervisor: if no port answers "TDK-LAMBDA", the supervisor falls back to `HVpowerSupply`, now the supply's fixed by-id name (`ASRL/dev/serial/by-id/usb-TDK-Lambda_Z+_Serial_Port_320B334-0005-if00::INSTR`; it was `ttyACM0`, the SPIN console). A Z+ answers `*IDN?` only after `INST:NSEL 1`, so after a power cycle the auto-detect misses it and the fallback is what finds it. If it enumerates but stays silent, select USB in the REM menu (REM → `INtF` → press voltage encoder → turn current encoder → press it).

7. **Plot windows off:** run the supervisor with `MPLBACKEND=Agg` (commands below). With plot windows (Tk), the second config of a group failed to open its devices on 27 Nov; headless, 3/3 passed. The SVG plots are still saved.
8. **Scope frames = current steps:** 7 phase writes (no lead-in since 27 Nov), the scope records `nbPointsI` = 7 segmented frames, frame i = current step i; the legacy `"Sequence"` key is ignored. **Open — check after every config:** the scope sometimes loses the first sweep triggers (the old "skip bug": 0, 2, 3 and 4 of the first writes lost in four 50 kHz dry runs). `results.json` then holds fewer distinct frames (repeated values in the last ones) and the last frame is the return to 3°. Never query the scope during a run: a status query also drops frames.
9. **Supply auto-detect:** the supervisor finds the supply by its USB vendor ID and selects it (`INST:NSEL`) before `*IDN?`, so it works after a power cycle; if no supply answers it stops with `HV power supply not found` instead of driving another port.

## 0b. First power: one point, supply by hand

`tools/single_point_manual.py` does one current step without touching the supply (it stays in LOCAL: press REM). Every step waits for Enter.
Scope 1 stays live the whole time (AUTO, triggered on the gate C1, FREQ/AMPL/RMS shown without statistics): you see the phase step happen, no screen reset.
The DMMs are triggered by software for this script: one 30-reading burst **before** the step (initial 3°) and one **during** (measurement phase), each with live scope values.
Sequence: Enter (setup, legs at 3°) → raise the supply, Enter (BEFORE burst) → Enter (phase step, DURING burst; the phase is held) → Enter (back to 3°) → lower the supply, Enter (legs off, IDLE, saved).

```bash
MPLBACKEND=Agg python3 tools/single_point_manual.py                  # 50 kHz, 0.5 A peak, 60 V
MPLBACKEND=Agg python3 tools/single_point_manual.py --ipeak 1.0      # next point
```

Check: 30 + 30 readings per DMM, Vbus/Idc/Pin before and during, scope 1 AMPL/2 near the asked Ipeak during. Ctrl-C stops the legs.

**Accelerated mode `--fast`** (commands below): no scope-1 frame screenshots and no 5 s plot pause; same sequence, delays and measurements (7 frames read with PAVA, 30 readings per DMM burst), scope 2 picture kept. 64 s per config instead of 94 (27 Nov). Drop `--fast` to get the per-frame pictures.

## 1. Anchors first: 50, 60, 70 kHz (≈ 10 min)

**Command center** (second terminal, venv active, leave it running all session): `python3 tools/command_center.py --watch 10`, then open `sessions/2026-11-27/command-center.html`. One page regenerated as each config's results land: configs done/missing, the go/no-go table below, P_remaining(f) per current step with September, loss breakdown, Ipeak AMPL/2 vs phase, Vbus sag, resonance candidates, scope screenshots. Works without internet.

```bash
MPLBACKEND=Agg python3 supervisor_script.py sessions/2026-11-27/base-config_A_anchors.json --fast
python3 calculations/loss_breakdown.py sessions/2026-11-27/configs/A_anchors
```

**Check before going on:** P_remaining(f) of the anchors against September (17.43 mW/kHz · f + 3.22 W, R² 0.999). Ipeak is read as AMPL/2; `--ipeak phase` is the cross-check. If they disagree by more than the scatter of September, stop and look (inductor value, probe scaling, scope measurement) before spending the session on the grid.

## 2. Grid: 23 points 10–100 kHz (≈ 45–60 min)

```bash
MPLBACKEND=Agg python3 supervisor_script.py sessions/2026-11-27/base-config_B_grid.json --fast
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
