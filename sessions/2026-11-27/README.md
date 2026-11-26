# Session 2026-11-27 — sweep configs (ticket #9)

Opposition-method campaign: **Vbus 60 V, 3.5 A peak, dead time 300 ns, DutyPWM 0.5**,
L = 40 µH (`InductorL`), 26 frequencies from 10 to 100 kHz. The 50/60/70 kHz anchors run first so they can be compared with the September session.

## Files

| Path | What it is |
|---|---|
| `base-config_A_anchors.json` | base config, group A: 50, 60, 70 kHz |
| `base-config_B_grid.json` | base config, group B: 23 log-spaced points, 10–100 kHz |
| `configs/A_anchors/PhaseShift/Voltage_60_<f>kHz/PhaseShift_Voltage_60V_Freq<f>kHz.json` | 3 run configs, consumed by `supervisor_script.py` |
| `configs/B_grid/PhaseShift/...` | 23 run configs |
| `configs/*/DutyShift/...` | duty-mode configs, also written by the generator. The supervisor does not use them. |

Both base configs are copies of the repository `base-config.json` with only these keys changed:
`Vmin = Vmax = 60`, `nbPointsV = 1`, `Imin = 0.5`, `Imax = 3.5`, `nbPointsI = 7`, `DeadTimePWM = 300`,
`frequencyPWM`, `ParentFolder = "sessions/2026-11-27/configs"`, `Experiment_name`.
Instrument addresses, delays, `VoltageLimit`, `Limited_PHI = 175` and `InitialPhaseShiftPWM = 3` are unchanged. `CurrentLimit` is 0.5 A (was 0.3 A): margin for power-on, phase steps and the capacitor-resonance points, so the supply never enters CC mode and sags Vbus silently; still caps the input at 30 W. Results are written next to the configs and git-ignored (`.gitignore` here). The scope also measures `RMS` on channel 2 (inductor current) for the processing script.

## Frequencies

* **A (anchors, run first):** 50, 60, 70 kHz.
* **B (grid):** `np.logspace(4, 5, 24)` rounded to whole kHz, which keeps the `Voltage_60_<f>kHz` folder names exact.
  The 50 kHz grid point is dropped because it duplicates an anchor. This leaves 23 points:
  10, 11, 12, 14, 15, 16, 18, 20, 22, 25, 27, 30, 33, 37, 41, 45, 55, 61, 67, 74, 82, 90, 100 kHz.

## Generating command (run from the repository root)

```bash
python3 Opposition_GenerateJson_v1_4.py sessions/2026-11-27/base-config_A_anchors.json
python3 Opposition_GenerateJson_v1_4.py sessions/2026-11-27/base-config_B_grid.json
```

The generator refuses to overwrite: delete `sessions/2026-11-27/configs/<group>` first if you regenerate.
The optional argument is the base-config path. Without it, the generator reads `./base-config.json` as before.

## Run order (from the repository root)

```bash
python3 supervisor_script.py sessions/2026-11-27/base-config_A_anchors.json   # 1) anchors 50, 60, 70 kHz
python3 supervisor_script.py sessions/2026-11-27/base-config_B_grid.json      # 2) 10–100 kHz grid
```

* Each group is a separate experiment folder, so the anchors are guaranteed to run before the grid.
  Inside a group, `supervisor_script.py` uses `os.walk` order, which is not sorted by frequency.
* The `interface.py` "Lancer Supervisor" button still reads the root `base-config.json`. To use the GUI, copy the group's
  base config over `base-config.json` first.
* Results are written next to each config (`dataOutputFolder` is relative to the repository, e.g.
  `sessions/2026-11-27/configs/A_anchors/PhaseShift/Voltage_60_50kHz/`). The supervisor refuses to run a group twice
  (`base-config-original.json` guard). Change `Experiment_name` and regenerate to rerun a group.

## Current points and the "3.5 A peak" choice

The generator treats `Imin..Imax` (`nbPointsI` points) as **peak** current: `ΔI = 2·Ipeak` and
`Phi = 360·ΔI·L·f / Vdc` (degrees, L in µH·1e-6). The September Excel analysed 3.5 A peak, so the campaign uses
**Ipeak = 0.5, 1.0, …, 3.5 A (7 points, 0.5 A step)**. Reasons for this choice:

* 3.5 A peak is the last point of every sweep.
* 0.5/1.5/2.5/3.5 A (the old 1 A grid) are still included.
* With a 0.5 A step, the lead-in point one step below 0.5 A is exactly **0°**. PhaseInit is therefore always 0, which is
  physically benign (no circulating current) and strictly below the first measurement point (OnlyScripts skip bug).

Sweep sent to the SPIN per file: `PhaseInit (0) → 0.5 A → … → 3.5 A` in `PhaseStep` increments (8 set-points).
Highest phase: 168° at 100 kHz, below `Limited_PHI = 175`.

## Phase resolution: float degrees vs firmware

The generator now writes float phases rounded to 2 decimals, and the supervisor sweep handles floats.
The SPIN sends `s_LEG2_p_<value>`, for example `s_LEG2_p_2.4`.
**Until ticket #7 lands, the firmware truncates the phase to an integer degree.** The column "int-trunc worst ΔI/I" gives
the worst current error over the 7 points caused by that truncation (Phi ∝ I, so the phase error equals the current error).
Points **below 30 kHz** are flagged: all their phases are small (2.4–45°), and truncation costs up to 31 %
(12 kHz, 0.5 A). Do not run the < 30 kHz group with an integer-only firmware if those points matter.

## Expected phase (degrees) per frequency and peak current — Vdc = 60 V, L = 40 µH

Run order = row order (A before B).

| # | Group | f (kHz) | PhaseInit (lead-in) | PhaseStep | 0.5 A | 1 A | 1.5 A | 2 A | 2.5 A | 3 A | 3.5 A | int-trunc worst ΔI/I | Flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | 50 | 0.00 | 12.00 | 12.00 | 24.00 | 36.00 | 48.00 | 60.00 | 72.00 | 84.00 | 0 % |  |
| 2 | A | 60 | 0.00 | 14.40 | 14.40 | 28.80 | 43.20 | 57.60 | 72.00 | 86.40 | 100.80 | 3 % |  |
| 3 | A | 70 | 0.00 | 16.80 | 16.80 | 33.60 | 50.40 | 67.20 | 84.00 | 100.80 | 117.60 | 5 % |  |
| 4 | B | 10 | 0.00 | 2.40 | 2.40 | 4.80 | 7.20 | 9.60 | 12.00 | 14.40 | 16.80 | 17 % | **< 30 kHz** |
| 5 | B | 11 | 0.00 | 2.64 | 2.64 | 5.28 | 7.92 | 10.56 | 13.20 | 15.84 | 18.48 | 24 % | **< 30 kHz** |
| 6 | B | 12 | 0.00 | 2.88 | 2.88 | 5.76 | 8.64 | 11.52 | 14.40 | 17.28 | 20.16 | 31 % | **< 30 kHz** |
| 7 | B | 14 | 0.00 | 3.36 | 3.36 | 6.72 | 10.08 | 13.44 | 16.80 | 20.16 | 23.52 | 11 % | **< 30 kHz** |
| 8 | B | 15 | 0.00 | 3.60 | 3.60 | 7.20 | 10.80 | 14.40 | 18.00 | 21.60 | 25.20 | 17 % | **< 30 kHz** |
| 9 | B | 16 | 0.00 | 3.84 | 3.84 | 7.68 | 11.52 | 15.36 | 19.20 | 23.04 | 26.88 | 22 % | **< 30 kHz** |
| 10 | B | 18 | 0.00 | 4.32 | 4.32 | 8.64 | 12.96 | 17.28 | 21.60 | 25.92 | 30.24 | 7 % | **< 30 kHz** |
| 11 | B | 20 | 0.00 | 4.80 | 4.80 | 9.60 | 14.40 | 19.20 | 24.00 | 28.80 | 33.60 | 17 % | **< 30 kHz** |
| 12 | B | 22 | 0.00 | 5.28 | 5.28 | 10.56 | 15.84 | 21.12 | 26.40 | 31.68 | 36.96 | 5 % | **< 30 kHz** |
| 13 | B | 25 | 0.00 | 6.00 | 6.00 | 12.00 | 18.00 | 24.00 | 30.00 | 36.00 | 42.00 | 0 % | **< 30 kHz** |
| 14 | B | 27 | 0.00 | 6.48 | 6.48 | 12.96 | 19.44 | 25.92 | 32.40 | 38.88 | 45.36 | 7 % | **< 30 kHz** |
| 15 | B | 30 | 0.00 | 7.20 | 7.20 | 14.40 | 21.60 | 28.80 | 36.00 | 43.20 | 50.40 | 3 % |  |
| 16 | B | 33 | 0.00 | 7.92 | 7.92 | 15.84 | 23.76 | 31.68 | 39.60 | 47.52 | 55.44 | 12 % |  |
| 17 | B | 37 | 0.00 | 8.88 | 8.88 | 17.76 | 26.64 | 35.52 | 44.40 | 53.28 | 62.16 | 10 % |  |
| 18 | B | 41 | 0.00 | 9.84 | 9.84 | 19.68 | 29.52 | 39.36 | 49.20 | 59.04 | 68.88 | 9 % |  |
| 19 | B | 45 | 0.00 | 10.80 | 10.80 | 21.60 | 32.40 | 43.20 | 54.00 | 64.80 | 75.60 | 7 % |  |
| 20 | B | 55 | 0.00 | 13.20 | 13.20 | 26.40 | 39.60 | 52.80 | 66.00 | 79.20 | 92.40 | 2 % |  |
| 21 | B | 61 | 0.00 | 14.64 | 14.64 | 29.28 | 43.92 | 58.56 | 73.20 | 87.84 | 102.48 | 4 % |  |
| 22 | B | 67 | 0.00 | 16.08 | 16.08 | 32.16 | 48.24 | 64.32 | 80.40 | 96.48 | 112.56 | 0 % |  |
| 23 | B | 74 | 0.00 | 17.76 | 17.76 | 35.52 | 53.28 | 71.04 | 88.80 | 106.56 | 124.32 | 4 % |  |
| 24 | B | 82 | 0.00 | 19.68 | 19.68 | 39.36 | 59.04 | 78.72 | 98.40 | 118.08 | 137.76 | 3 % |  |
| 25 | B | 90 | 0.00 | 21.60 | 21.60 | 43.20 | 64.80 | 86.40 | 108.00 | 129.60 | 151.20 | 3 % |  |
| 26 | B | 100 | 0.00 | 24.00 | 24.00 | 48.00 | 72.00 | 96.00 | 120.00 | 144.00 | 168.00 | 0 % |  |
