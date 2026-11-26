# calculations

## Loss breakdown (`loss_breakdown.py`)

Python port of Nicolas's loss-breakdown workbook
[`Calculs-EssaiOct26-Manipe16Sept.xlsx`](Calculs-EssaiOct26-Manipe16Sept.xlsx)
(sheet `Calcul`, 16 Sept 2026 session: 60 V, 3.5 A peak, 300 ns dead time,
50/60/70 kHz). For each operating point it computes, exactly as the workbook:

| term | formula (Excel row) |
|---|---|
| input power | `P_in = Vbus * I_dc` (27) |
| MOSFET conduction, dead-time corrected | `Rmos2*Irms² - 4*(td/Ts)*Rmos2*Ipeak²` (28, 33, 34) |
| inductor DC resistance | `R_ind*Irms²` (30) |
| capacitor ESR | `R_esr*Irms_cap²`, `Irms_cap = Ipeak*sqrt(2*t_phi/(3*Ts))`, `phi = Ipeak*4*180*L/(Ts*Vbus)` (31, 44, 45, 51) |
| body diodes during dead time | `n_diodes*Vdiode*Ipeak*td/Ts` (32) |
| remaining | `P_remaining = P_in - all of the above` (36) |

`Irms` is the inductor RMS current **measured on the scope** (row 48); if a
session has no scope RMS measurement the equation of row 46 is used and the
output says so (`irms_source = equation`).

Then, for points sharing the same Vbus/Ipeak (a *group*) at several
frequencies, it fits `P_remaining(f) = slope*f + intercept` (least squares,
= Excel `LINEST`), gives `Eoff = 1000*slope/4` µJ per switch and
`P_fixed = P_remaining - slope*f` (row 43).

On the reference workbook it gives
`P_remaining(f) = 17.43 mW/kHz * f + 3.220 W`, `Eoff = 4.3572 µJ`.

### Usage

```bash
# the reference workbook (uses its own measured inputs)
python calculations/loss_breakdown.py calculations/Calculs-EssaiOct26-Manipe16Sept.xlsx

# a session folder written by the supervisor (ParentFolder/Experiment_name,
# containing PhaseShift/Voltage_<V>_<F>kHz/ with DMM CSVs, results.json, PhaseShift_*.json)
python calculations/loss_breakdown.py path/to/session -o breakdown.csv

# a hand-made table of points (columns: group, vbus_V, i_dc_A, ipeak_A, f_kHz,
# L_uH, td_us, irms_ind_A [, circuit parameters])
python calculations/loss_breakdown.py points.csv
```

Options: `--params p.json` overrides the circuit parameters
(`r_esr_cap_ohm` 0.125, `r_ind_dc_ohm` 0.2, `r_mos2_ohm` 0.2059, `v_diode_V`
0.845, `n_diodes_deadtime` 4 by default; a `LossModel` dict in the session's
PhaseShift json is also honoured). `--ipeak scope|scope-pp|phase` chooses where
Ipeak comes from in a session folder: the scope `AMPL` value as in
`TraitementV10.py` (default), half of it, or `Vbus*phase/180/(4*L*f)` from
the phase table.

Session folders are read with `TraitementV10.read_supervisor_series` and
`TraitementV10.segment_means` (same CSV parsing and per-step averaging as
`TraitementV10.py`). To get Irms from the scope, add
`{"type": "RMS", "channel": <current channel>}` to `ScopeAutoMeasure` in
`base-config.json`.

### Test

```bash
python -m pytest calculations/test_loss_breakdown.py -v
```

Compares the script with the values cached in the workbook at 50/60/70 kHz
(relative tolerance 1e-9: same closed-form formulas) and with the report's
figures 17.43 mW/kHz (±0.005), 3.22 W (±0.005 W), 4.3572 µJ (±5e-5). It also
writes a synthetic session folder carrying the workbook's measured inputs and
checks that the CLI reproduces the same numbers from it.

The raw files of the 16 Sept session (DMM CSVs, scope captures) were not found
in the repository, so the reference check uses the workbook's own measured
inputs (Vbus, DC current, Ipeak, scope Irms).
