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
`TraitementV10.py`, half of it (default, AMPL is peak-to-peak), or
`Vbus*phase/180/(4*L*f)` from the phase table. Step-by-step guide for
running the script by hand: [HOWTO.md](HOWTO.md).

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

## Open questions on the model (for Nicolas, session of 2026-11-27)

The script follows the reference workbook formula by formula (decision 2026-11-26: keep the formulas for now). Questions to settle with Nicolas:

1. **Dead-time correction of the MOSFET conduction loss (sheet `Calcul`, row 33).** The session report says P_mos × (1 − td/Ts); the workbook computes P_mos = Rmos·Irms² − 4·(td/Ts)·Rmos·Ipeak². Why the factor 4, and why Ipeak² rather than Irms²?
2. **Input power.** P_in = "I DC condo" × Vbus, with "I DC condo" under a section labelled *Simu*. Is it the measured DC input current?
3. **Peak current.** The scope `AMPL` is peak-to-peak (Luiz, 2026-11-26), so Ipeak = AMPL / 2 is now the default (`--ipeak scope-pp`); `--ipeak phase` (Vbus·φ/180/(4·L·f)) is the cross-check. Confirm on the anchor points.
4. **Scope RMS current.** The 2026-11-27 configs add `{"type": "RMS", "channel": 2}` to `ScopeAutoMeasure`, assuming channel 2 is the inductor current; without it the script falls back to the RMS equation (row 46). RMS over the screen vs cycle RMS (`CRMS`): which one did the workbook use?
5. **The 3.22 W intercept** is the least-squares intercept; the per-point P_fixed (row 43) are 3.2174, 3.2261, 3.2174 W.
6. **Fit grouping.** Points are grouped by bus voltage and phase-step index across frequencies; this assumes one step index = one peak current at every frequency, true when the phase table scales with f (as the generator does).
7. **Raw data of 2026-09-16.** Not in the repo; it is on the LAPLACE share (`COMMUN\CS_Banc_Caract_Pertes_T\Documentation\réunions\2026\Session-Octobre2026`), with the HV capacitor characterisation. Running the script on it closes the check against raw data.
