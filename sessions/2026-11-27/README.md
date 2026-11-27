# Session 2026-11-27 — sweep configs (ticket #9)

Opposition-method campaign: **Vbus 60 V, 3.5 A peak, dead time 300 ns, DutyPWM 0.5**,
L = 40 µH (`InductorL`), 26 frequencies from 10 to 100 kHz. The 50/60/70 kHz anchors run first so they can be compared with the September session.

## Files

| Path | What it is |
|---|---|
| `base-config_A_anchors.json` | base config, group A: 50, 60, 70 kHz |
| `base-config_B_grid.json` | base config, group B: 10 points, 10–100 kHz in 10 kHz steps (27 Nov; was 23 log-spaced) |
| `configs/A_anchors/PhaseShift/Voltage_60_<f>kHz/PhaseShift_Voltage_60V_Freq<f>kHz.json` | 3 run configs, consumed by `supervisor_script.py` |
| `configs/B_grid/PhaseShift/...` | 10 run configs |
| `configs/*/DutyShift/...` | duty-mode configs, also written by the generator. The supervisor does not use them. |

Both base configs are copies of the repository `base-config.json` with only these keys changed:
`Vmin = Vmax = 60`, `nbPointsV = 1`, `Imin = 0.5`, `Imax = 3.5`, `nbPointsI = 7`, `DeadTimePWM = 300`,
`frequencyPWM`, `ParentFolder = "sessions/2026-11-27/configs"`, `Experiment_name`.
`HVpowerSupply` is the supply's fixed by-id name (27 Nov; `ttyACM0` was the SPIN console), and the legacy `Sequence` key is gone (the scope records `nbPointsI` frames). Other instrument addresses, delays, `VoltageLimit`, `Limited_PHI = 175` and `InitialPhaseShiftPWM = 3` are unchanged. `CurrentLimit` is 0.2 A since 27 Nov (was 0.5 A, 0.3 A before): 12 W at 60 V; the 50 kHz anchor peaks at 7.8 W (0.13 A) with 0.15 V of Vbus sag. Watch Vbus at the capacitor-resonance points: if the supply enters CC mode it sags Vbus silently. Results are written next to the configs and git-ignored (`.gitignore` here). The scope also measures `RMS` on channel 2 (inductor current) for the processing script.

## Frequencies

* **A (anchors, run first):** 50, 60, 70 kHz.
* **B (grid):** 10, 20, 30, 40, 50, 60, 70, 80, 90, 100 kHz (10 points, decision 27 Nov; the first plan was 23 log-spaced points).
  50/60/70 kHz are in both groups: the grid runs them with the duty trim, the anchors ran without it.

## Generating command (run from the repository root)

```bash
python3 Opposition_GenerateJson_v1_4.py sessions/2026-11-27/base-config_A_anchors.json
python3 Opposition_GenerateJson_v1_4.py sessions/2026-11-27/base-config_B_grid.json
```

The generator refuses to overwrite: delete `sessions/2026-11-27/configs/<group>` first if you regenerate.
The optional argument is the base-config path. Without it, the generator reads `./base-config.json` as before.

## Run order (from the repository root)

```bash
MPLBACKEND=Agg python3 supervisor_script.py sessions/2026-11-27/base-config_A_anchors.json   # 1) anchors 50, 60, 70 kHz
MPLBACKEND=Agg python3 supervisor_script.py sessions/2026-11-27/base-config_B_grid.json      # 2) 10–100 kHz grid
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
Sweep sent to the SPIN per file: `0.5 A → … → 3.5 A` in `PhaseStep` increments (7 set-points, one scope frame each).
The 0° lead-in of 26 Nov was removed on 27 Nov: the scope recorded it as frame 1 and dropped 3.5 A.
Highest phase: 168° at 100 kHz, below `Limited_PHI = 175`.

## Phase resolution: float degrees vs firmware

The generator now writes float phases rounded to 2 decimals, and the supervisor sweep handles floats.
With the string protocol the supervisor sends `s_LEG2_p_<value>`, for example `s_LEG2_p_2.4`. The session configs now use
ThingSet (`"shield_protocol": "thingset"`, ticket #16): the phase is written as a float to `Config/Leg2/wPhaseShift_deg`,
so no truncation once the firmware implements that object.
**Until ticket #7 lands, the firmware truncates the phase to an integer degree.** The column "int-trunc worst ΔI/I" gives
the worst current error over the 7 points caused by that truncation (Phi ∝ I, so the phase error equals the current error).
Points **below 30 kHz** are flagged: all their phases are small (2.4–45°), and truncation costs up to 31 %
(12 kHz, 0.5 A). Do not run the < 30 kHz group with an integer-only firmware if those points matter.

## Expected phase (degrees) per frequency and peak current — Vdc = 60 V, L = 40 µH

Run order = row order (A before B).

| # | Group | f (kHz) | PhaseInit | PhaseStep | 0.5 A | 1 A | 1.5 A | 2 A | 2.5 A | 3 A | 3.5 A | int-trunc worst ΔI/I | Flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | 50 | 12.00 | 12.00 | 12.00 | 24.00 | 36.00 | 48.00 | 60.00 | 72.00 | 84.00 | 0 % |  |
| 2 | A | 60 | 14.40 | 14.40 | 14.40 | 28.80 | 43.20 | 57.60 | 72.00 | 86.40 | 100.80 | 3 % |  |
| 3 | A | 70 | 16.80 | 16.80 | 16.80 | 33.60 | 50.40 | 67.20 | 84.00 | 100.80 | 117.60 | 5 % |  |
| 4 | B | 10 | 2.40 | 2.40 | 2.40 | 4.80 | 7.20 | 9.60 | 12.00 | 14.40 | 16.80 | 17 % | **< 30 kHz** |
| 5 | B | 20 | 4.80 | 4.80 | 4.80 | 9.60 | 14.40 | 19.20 | 24.00 | 28.80 | 33.60 | 17 % | **< 30 kHz** |
| 6 | B | 30 | 7.20 | 7.20 | 7.20 | 14.40 | 21.60 | 28.80 | 36.00 | 43.20 | 50.40 | 3 % |  |
| 7 | B | 40 | 9.60 | 9.60 | 9.60 | 19.20 | 28.80 | 38.40 | 48.00 | 57.60 | 67.20 | 6 % |  |
| 8 | B | 50 | 12.00 | 12.00 | 12.00 | 24.00 | 36.00 | 48.00 | 60.00 | 72.00 | 84.00 | 0 % |  |
| 9 | B | 60 | 14.40 | 14.40 | 14.40 | 28.80 | 43.20 | 57.60 | 72.00 | 86.40 | 100.80 | 3 % |  |
| 10 | B | 70 | 16.80 | 16.80 | 16.80 | 33.60 | 50.40 | 67.20 | 84.00 | 100.80 | 117.60 | 5 % |  |
| 11 | B | 80 | 19.20 | 19.20 | 19.20 | 38.40 | 57.60 | 76.80 | 96.00 | 115.20 | 134.40 | 1 % |  |
| 12 | B | 90 | 21.60 | 21.60 | 21.60 | 43.20 | 64.80 | 86.40 | 108.00 | 129.60 | 151.20 | 3 % |  |
| 13 | B | 100 | 24.00 | 24.00 | 24.00 | 48.00 | 72.00 | 96.00 | 120.00 | 144.00 | 168.00 | 0 % |  |
