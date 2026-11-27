# Session log — Open-Power bench, 27 November 2026

Operating point: 60 V · 3.5 A peak (0.5–3.5 A, 7 points) · 300 ns dead time · D = 0.5 · L = 40 µH. Plan: [RUN_SHEET.md](RUN_SHEET.md). Map: luizvilla/test_bench_code#1.

## Setup

| | |
|---|---|
| People | |
| Firmware flashed | `bench-thingset-554f8b9a.mcuboot.bin` / fallback: |
| SPIN serial (`-if02` port) | |
| Scope / DMM / supply as configured | yes / no: |
| Smoke test (50 kHz, LEG2 lag 0.583 µs, GPIO 9 pulse 2.1 ms) | |

## Anchors: go/no-go

| f (kHz) | P_remaining, AMPL/2 (W) | P_remaining, `--ipeak phase` (W) | September (W) | Δ (W) |
|---|---|---|---|---|
| 50 | 3.601 | 3.614 | 4.089 | −0.488 (−11.9 %) |
| 60 | 4.134 | 4.143 | 4.272 | −0.138 (−3.2 %) |
| 70 | 3.990 | 4.001 | 4.437 | −0.447 (−10.1 %) |

Verdict (GO / NO-GO) and why:

## Grid (23 points)

| | |
|---|---|
| Folders complete | /23 |
| Missing or failed points, and why | |
| Candidate capacitor-resonance frequencies (log only, excluded in #13) | |
| Fit of P_remaining(f) | |

## Dead-time compensation A/B (optional)

| f (kHz) | P_remaining, comp off (W) | P_remaining, comp on (W) | mean iL on scope, off / on |
|---|---|---|---|
| 50 | | | |
| 60 | | | |
| 70 | | | |

## Timeline

<!-- HH:MM: what was done or observed, what was decided -->

- 11:07: SPIN flashed over USB (mcumgr) with `bench-thingset-554f8b9a.mcuboot.bin`; it was still on the string firmware (enumerated as `COMM-MASTER`, PID 0x0101). Now `TWIST_V1_4_2`, `-if00` → ttyACM0, `-if02` → ttyACM1.
- 11:09–11:12: **HV supply (TDK-Lambda Z+) not visible on USB** although the cable was plugged in and the supply in remote. `lsusb` did not list it; the kernel log showed it failing to enumerate on port 3-4: `device descriptor read/64, error -71`, `device not accepting address …, error -71`, `unable to enumerate USB device` (USB signal error). Checking the cable and remote mode did not help.
- 11:16: **Fix: power-cycled the supply** with the USB cable plugged in. It enumerated at once as `TDK-Lambda Z+ Serial Port` (2504:0001, serial 320B334-0005) on ttyACM2.
- 11:17: Supply enumerated but **does not answer `*IDN?`** (no reply at 9600/19200/57600/115200, LF/CRLF/CR). Front panel has no USB key, only REM. Next: select the interface from the REM menu (REM → `INtF` → press voltage encoder → turn current encoder to the USB entry → press current encoder).
- 11:2x: USB selected in the REM menu. The supply still ignored a bare `*IDN?`: the Z+ only answers after `INST:NSEL 1` (address 1). Then `TDK-LAMBDA,Z650-1,320B334-0005,3.002`. Dry-run config uses `HVpowerSupply = ASRL/dev/serial/by-id/usb-TDK-Lambda_Z+_Serial_Port_320B334-0005-if00::INSTR`.
- Supply driven from the PC through `TDKZ650_1_U` (output cable off the board, 0.1 A limit): 0→10 V in 2 V steps, measured 1.986 / 3.995 / 5.992 / 7.990 / 9.988 V, ramp down to 0.010 V, output OFF, no error. Auto-detect found it on ttyACM2 (it answered `*IDN?` once selected).
- 11:28: LEG2 phase checked roughly on scope 1 C4 (not a clean gate, no input voltage): C1→C4 skew follows the commanded phase within ~0.3 µs at 10.5/45/90/135/180° (50 kHz).
- 11:28:09: **supply dropped off USB again** (`usb 3-4: USB disconnect`), ~3 min after the 0→10 V ramp, with no command in flight; no re-enumeration attempt in the kernel log afterwards.
- 11:29: supervisor dry run on `A_anchors_dry` stopped on the first config: `Failed to open HV power supply … No such file or directory`. The supervisor **does not abort** when the supply is missing: it ran the SPIN setup, skipped output ON / ramp / phase sweep (exceptions collected), turned the legs off, then crashed reading the empty DMM buffer (`dmm_get_buffer`: buffer `NULL` → `ValueError: invalid literal for int() … 'U'`). SPIN set to IDLE afterwards.
- 11:31:21: **Linux desktop session crashed** (logind `Removed session 2`, re-login 11:31:31; no reboot, up since 09:32; no segfault/OOM in the journal). Afterwards the scopes and DMMs looked frozen: they were where the supervisor left them (DMMs armed for 7 external triggers, scopes in SINGLE/segmented). Recovered over LAN: DMMs `ABORt`/`*RST`/`*CLS` (now IMM trigger, 1 sample), scopes `:ACQuire:SEQuence OFF`, `:HISTORy OFF`, `:TRIGger:MODE AUTO`. The supply was still off USB.
- 11:37: supply still off USB after a power cycle; laptop port `usb3-port4` reported `not attached` (no electrical contact, no `-71` either). 11:38: **moved the USB cable to another port** (USB-C dock, 3-5.2): supply back on ttyACM2, answers after `INST:NSEL 1`.
- 11:39: dry run attempt 2. **50 kHz config complete**: supply ON, ramp to 60 V (scope 2 C3 TOP = 60.0 V), phase sweep 0→84° (all writes read back), ramp down, supply OFF, both DMM buffers read (7 × 30 samples), scope measures saved (FREQ 49 997 Hz). **60 kHz config failed** in `open_all_devices()` right after the DMMs opened; the supervisor never prints its `errors` list, so the cause is hidden. The only clue is a Tk error from matplotlib (`main thread is not in main loop`) after config 1 had shown plot windows (`plt.show(block=False)`, `plt.pause(5)`). `open_all_devices()` on the same config alone works. Then crashed in `finally` (`Microcontroller is not opened`).
- 11:41: dry run attempt 3, from a clean `A_anchors_dry`, with `MPLBACKEND=Agg` (no plot windows, SVGs still saved) and open/setup exceptions printed.
- 11:45: **dry run attempt 3: 3/3 configs PASS** (50/60/70 kHz). Each: supply opened (auto-detect, ttyACM2), ON, ramp to 60 V (scope 2 C3 TOP 60.0 V), 8 phase writes 0→84/100.8/117.6° all read back, ramp down, OFF, DMM buffers read, scope measures + bitmaps saved, `base-config-original.json` written. So the 60 kHz failure of attempt 2 came from the plot windows of config 1 (Tk): **run the real groups with `MPLBACKEND=Agg`**. Scope FREQ 49 998 / 60 006 / 70 014 Hz (one 70 kHz frame returned None).
- `loss_breakdown.py` parses the dry-run group (all NaN without input, as expected). `command_center.py` builds the page. Dry-run results moved out of `configs/` to the session scratchpad.
- **Open before §1:** (a) only **3 scope frames** are captured per config (`"Sequence": 3` in both base configs) while 7 current steps are swept, so steps 4–7 (up to 3.5 A) get no scope AMPL/RMS and `loss_breakdown` falls back to the equation for Ipeak/Irms. (b) the 26 generated configs still have `HVpowerSupply = ASRL/dev/ttyACM0::INSTR` (the SPIN console); auto-detect found the supply today, but after a supply power cycle a bare `*IDN?` gets no answer and the fallback would hit the SPIN.
- 12:2x: **fix: scope frames = current steps.** `SDS2104X_plus` now records `nbPointsI` frames (7) and ignores the legacy `"Sequence"` key (test `tests/test_scope_frames.py`); `"Sequence"` removed from `base-config.json` and both session base configs. `HVpowerSupply` set to the by-id name in both base configs; A_anchors and B_grid regenerated (diff: only these two keys).
- 50 kHz retest (headless, results in the session scratchpad): supply ON → 60 V → OFF, 8 phase writes read back, **7 frames saved**. Tagged run (a distinct extra pause after each sweep write, no scope polling): frame gaps 0.626/0.726/…/1.126 s = **writes 1–7**, i.e. **frame 1 = 0° lead-in, frames 2–7 = 0.5…3.0 A, 3.5 A not recorded**. `loss_breakdown` pairs frame i with step i, so scope values are one step off.
- **DMMs follow the scope trigger:** `FALLINGEDGES` on the DMM-complete channels (scope 2 C2/C4) was 90 = 3 × 30 with `Sequence: 3`, and 210/180 with 7 frames. So `Sequence: 3` also cut the DMM data to 3 steps (then split into 7 by `segment_means`). Inference: the scope's trigger output triggers the DMMs.
- **Intermittent:** in 2 of 3 supervisor runs at 50 kHz the scope lost the first 2–3 sweep pulses (only 5–6 frames, still `Ready` after the sweep). Not reproduced outside the supervisor (scope alone, scope + armed DMMs: 8/8 every time, at 0.6 s and 1–2 s spacing). Polling `:TRIGger:STATus?` during a sweep also drops frames: do not poll the scope during a run.
- **Open, decide before §1:** record the lead-in too (`nbPointsI + 1` frames and DMM `TRIG:COUN`, processing skips frame/segment 1) or remove the lead-in write.
- 13:3x: **lead-in removed** (decision Luiz): it was added on 26 Nov (#9, commit 3b93f90) against an "OnlyScripts skip bug"; in September the sweep had no lead-in (12…84° at 50 kHz). Generator: `PhaseInit` = first current step; 26 configs regenerated (only `PhaseInit` changes, 7 writes each). `loss_breakdown` still skips the lead-in of 26-Nov configs.
- **Supply auto-detect deployed:** `TDKZ650_1_U.open_hv_power_supply` tries only ports with the TDK-Lambda USB vendor ID (0x2504), then the configured `HVpowerSupply`; sends `INST:NSEL <HVpowerSupplyAddress, default 1>` before `*IDN?`; accepts only "TDK-LAMBDA"; raises `HV power supply not found` otherwise (no more writes to the SPIN ports, no more 5 s probing of 32 ttyS ports). Tested: supply deselected with `INST:NSEL 6` (state after a power cycle) → found in 0.5 s, alone and inside the supervisor.
- 13:44: 50 kHz supervisor dry run, no lead-in, tagged write pauses: writes 12→84° all read back, but the scope kept only **4 frames = 60°, 72°, 84° and the final 3°**: the first 4 sweep triggers were lost. So the "skip bug" is real and intermittent (lost 2, 3, 0, 4 of the first triggers in four runs); the lead-in did not cure it. Scope 2 counted 210/180 DMM edges in that run while scope 1 kept 3 sweep frames, so the DMMs do not follow scope 1's trigger (earlier inference withdrawn). One DMM returns fewer bursts than the other (180 = 6 × 30): Luiz sees it on the Vbus scope too.
- 13:49: **scope 1 measures off screen** (Luiz: the measurement panel cluttered the PWM screen): `:MEASure OFF` at setup, each frame read with `Cn:PAVA? <type>` (`GetParam`); scope 2 unchanged. 50 kHz run: 7 frames = writes 12…84° (tagged gaps), FREQ 50 000 Hz on every frame, AMPL/RMS per frame in `results.json`. Current DMM returned 180 readings (6 bursts), voltage DMM 210.
- DMM burst time (testbench settings, NPLC 0.5, 30 samples, bus trigger, no polling): **0.30–0.45 s**, inside the 0.626 s phase step (0.6 s `delay_com` + 0.026 s ThingSet write). Polling `DATA:POINts?` during a burst stretches it to 1.02 s.
- Delays: all base-config delays equal Nicolas's 16 Sep "Tested OK" values (`f4b9c83`: `delay_com` 0.1 → 0.6, DMM samples 3 → 30); not changed today. The string protocol `sendCommand` was write + `sleep(delay)`, so the step length is unchanged (0.60 → 0.626 s).
- 14:0x: **DMM missed bursts.** Both DMMs share one trigger line (Luiz); identical settings (EXT, POS, TRIG:DEL 1 µs, TRIG:COUN 7, SAMP:COUN 30). Two miss modes seen:
  - Supervisor run 13:48 (scope 2 screenshot): voltage DMM 7 bursts, **current DMM missed the 6th** (1.03 s after the 5th, mid-plateau): not a busy/too-fast problem.
  - Bench test without HV (scope armed, both DMMs armed as the supervisor does, 7 writes at 0.626 s, count read 0.5 s after each write): with 2.5 s between DMM setup and first trigger, the **voltage DMM missed trigger 1** in 4/5 sweeps; with 6 s, 0 misses in 3/3. The current DMM never missed in this test.
  - GPIO 9 pulse is the same as the string firmware's (21 control periods = 2.1 ms, `owntech/main.cpp` on ReleaseCandidate); September used `delay_com` 0.6 too.
- 14:03: **`dmm_init_delay` 2 → 4 s** (both base configs, 26 configs regenerated, only this key). 50 kHz validation run, normal timing, supply to 60 V: **7/7 scope frames** (0.626 s apart = writes 12…84°), **both DMMs 210 readings** (7 × 30; scope 2 FALLINGEDGES 210/210), off-screen FREQ 50 000 Hz per frame. Board input still disconnected: scope 2 C3 (supply side) TOP 60 V, but voltage DMM ≈ 0 V and iL ≈ noise, so `loss_breakdown` has no power to compute.
- 14:1x: `tools/single_point_manual.py` (one point, supply by hand, never opened by the script). Tested without input voltage at 50 kHz / 0.5 A (12°): SPIN setup and stop OK, 30 + 30 DMM readings, scope 1 frame FREQ 50 000 Hz, `loss_breakdown` reads the folder.
- 13:16–13:53: **grid dry run, B_grid, 23 configs** (supply to 60 V, board input disconnected; results in the session scratchpad): **23/23, no exception, 7/7 frames on every config** (gaps 0.62–0.66 s = the 7 writes), **DMMs 210/210 on every config**, voltage DMM ≈ 0 V throughout. **94 s per config, 37.5 min for the grid** (A_anchors ≈ 5 min). Per config: open 5.4 s, setup 11.6 s (incl. `dmm_init_delay` 4 s), ramp up 1.7 s, sweep 4.3–4.6 s, ramp down 1.7 s, `plt.pause` 5.1 s, **scope saves 51.6 s** (7 frames × 2 bitmaps + scope 2). Time at 60 V per config ≈ 8 s.
- Scope 1 FREQ returned `****` at 12, 25, 67 kHz (all frames) and 14, 27 kHz (some): the timebase gives ≈ 1.2 periods on screen (`one_period*1.2/10`, rounded to the scope's steps), too short at those frequencies; 10 kHz (2 periods) is fine. Same window for RMS: if RMS is computed over the screen, a non-integer number of periods biases it (cf. "RMS vs cycle RMS" for Nicolas).
- 14:2x: **scope 1 timebase ≥ 2 periods** (smallest 1-2-5 step showing 2 full periods; was ≈ 1.2): 2.0–3.4 periods on screen over the grid. Bench check, live gate signal: FREQ correct at 10, 12, 14, 25, 27, 50, 67, 100 kHz (12/25/67 failed before). Applies to the supervisor and `single_point_manual.py` (same `oscilloscope_setup`).
- 14:3x: single point too fast at the bench (Luiz). `single_point_manual.py` reworked: scope 1 live all the time (AUTO on C1, measurements shown without statistics, values read live with PAVA), every step on Enter, phase held until Enter, DMMs on software trigger: 30 readings BEFORE the step (3°) and 30 DURING. Tested without input voltage: 30 + 30 per DMM, scopes AUTO after.
- 14:5x: **`--fast`** for `supervisor_script.py` (no scope-1 frame bitmaps, no `plt.pause(5)`, scope 2 picture kept) and **`CurrentLimit` 0.5 → 0.2 A** (both base configs, configs regenerated, only this key; supply reads back 0.19999 A).
- 14:5x: anchors in `--fast` meant as a dry run, but **the board was connected** (Luiz: fine): the 5 V guard stopped after 50 kHz. **First powered config, 50 kHz, 60 V, 0.2 A limit:** 7/7 frames, 210/210 DMM readings, Vbus 59.98 → 59.83 V (no CC), Pin 0.26 → 7.78 W. Ipeak AMPL/2 0.67/1.04/1.47/2.04/2.54/3.04/3.54 A vs phase 0.50/1.00/…/3.49 A. **P_remaining at 3.5 A: 3.83 W (AMPL/2 and phase agree) vs September 4.089 W (−0.26 W, −6 %)**. 64 s for the config in `--fast` (scope-1 value reads 19 s, scope 2 pictures 7.6 s).
- 14:21–14:24: **A_anchors, real, `--fast`** (60 V, 0.2 A limit): 3/3 configs, 7/7 frames, 210/210 DMM readings, FREQ exact, Vbus 59.83–59.84 V at 3.5 A, 3 min. At 3.5 A: Ipeak AMPL/2 3.54–3.57 A vs phase 3.49 A; Pin 7.48 / 7.80 / 7.24 W; P_remaining (table above). Fit over 3.5 A: 19.4 mW/kHz · f + 2.74 W, R² 0.50 (September 17.43 mW/kHz · f + 3.22 W, R² 0.999). Repeatability: the 14:5x 50 kHz config gave 3.83 W, this run 3.60 W. Breakdowns: `A_anchors_breakdown.csv`, `A_anchors_breakdown_phase.csv`; command center regenerated.
- 15:0x: DC offset seen on the inductor current (Luiz). `single_point_manual.py --dtc off|on|ab`: `ab` measures DURING with dead-time compensation off, then switches it on at the same held point (third DMM burst + scope reading); iL mean (MEAN C2) added to the scope measures and the summary. Single point default 10 kHz, initial phase ≤ half the step. Not yet run on the bench.
- 14:35: **iL DC offset sweep** (`tools/offset_sweep.py`, powered, 60 V, 2 A peak, 0.2 A limit; data `configs/offset_sweep/20261127-143547/`). Offset at D = 0.5, compensation off, probe zero subtracted: **−0.046 A at 50 kHz, −0.044 A at 100 kHz** (~1 % of the 4 A pp ripple). Common duty correction (what the firmware compensation does): +1.6 / +1.9 A per unit duty, nearly no effect; firmware compensation ON: −0.033 / −0.017 A. Differential correction (D1 − D2): **−86 A per unit duty at both f**, zero at **Δ = −0.00033 / −0.00035**. Offset and cancelling Δ do not scale with f: **not a dead-time effect**; the dead-time formula is not changed. Steeper slope near Δ = 0 (dead-time sign flip with current direction). Loop DC resistance from the slope: 60/86 ≈ **0.70 Ω** (configs: `TotalR` 0.42 Ω). To do: same sweep at 0.5 and 3.5 A before deciding a differential trim.
- Note for the supervisor: `TDKZ650_1_U.open_hv_power_supply` sends `*IDN?` to every ttyACM port and, if none answers "TDK-LAMBDA", falls back to the config address `ASRL/dev/ttyACM0`, which is now the SPIN console. Do not start a run until the supply answers `*IDN?`.

## Answers from Nicolas

1. Dead-time term (4·(td/Ts)·Rmos·Ipeak²):
2. "I DC condo":
3. Ipeak = AMPL/2:
4. RMS vs CRMS:
5. Fit grouping:
6. LAPLACE share access (#15):

## Handover to #13

- [ ] `sessions/2026-11-27/configs/` copied to lab storage (where:)
- Points to exclude and why:
- Open issues for the report:
