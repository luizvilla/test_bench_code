# How to run the loss-breakdown script (step by step)

*Draft, 27 Nov 2026.*

This guide is for people who have not used `loss_breakdown.py` before. You type every command yourself, and no AI tool is needed. The script does the same calculations as Nicolas's Excel workbook `Calculs-EssaiOct26-Manipe16Sept.xlsx`, sheet `Calcul`. You can run it on that workbook, on a folder of bench results, or on a table of points you type in yourself. It gives the loss breakdown for each point, then fits P_remaining against f and gives Eoff.

For the formulas and the Excel row each one comes from, see [README.md](README.md). This guide only covers how to run the script.

---

## 1. One-time setup (about 5 minutes)

You need **Python 3.10 or newer** (`python3 --version`; on Windows, `py --version`) and a copy of this repository on branch `session-2026-11-27`.

Open a terminal **in the repository's top folder** (the one that contains `supervisor_script.py`). Every command below starts from there.

Create a private Python environment and install the libraries:

**Linux / macOS**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Once the environment is active, `(.venv)` appears at the start of the prompt. Activate it again (`source .venv/bin/activate` or `.venv\Scripts\Activate.ps1`) **every time you open a new terminal**.

> **Why the environment matters:** without it the script may use your system's pandas and numpy. On our Linux machine that combination crashes with `ValueError: numpy.dtype size changed`. Inside `.venv` it works.

## 2. Check that it works: rerun the Excel workbook

```bash
python calculations/loss_breakdown.py calculations/Calculs-EssaiOct26-Manipe16Sept.xlsx
```

You should see this (the important line is the last one):

```
group  f_kHz  vbus_V  ipeak_A  irms_used_A irms_source  p_in_W  p_mos_W  p_inductor_W  p_cap_esr_W  p_diode_deadtime_W  p_remaining_W  p_fixed_W
excel     50 59.7918   3.5000       2.9744       scope  7.9450   1.6703        1.7694       0.2390              0.1774         4.0888     3.2174
excel     60 59.7918   3.5000       2.8731       scope  7.9406   1.5180        1.6509       0.2868              0.2129         4.2719     3.2261
excel     70 59.7928   3.5000       2.7626       scope  7.9064   1.3595        1.5264       0.3346              0.2484         4.4374     3.2174

[excel] P_remaining(f) = 17.43 mW/kHz * f + 3.220 W  (n=3, R2=0.9992)  -> Eoff = 4.3572 uJ per switch
```

These are the workbook's numbers: 17.43 mW/kHz, 3.22 W and Eoff 4.36 µJ. If you get them, the setup is correct.

To run the full automatic check (it should end with `12 passed`):

```bash
python -m pytest calculations/test_loss_breakdown.py
```

## 3. Run it on bench results

The supervisor writes each session's results into the folder named by `ParentFolder` / `Experiment_name` in the config. For 27 November these are:

- `sessions/2026-11-27/configs/A_anchors` (50/60/70 kHz anchors)
- `sessions/2026-11-27/configs/B_grid` (10–100 kHz grid)

Each one contains a `PhaseShift/Voltage_<V>_<F>kHz/` folder for each frequency. Point the script at the session folder, not at a subfolder inside it:

```bash
python calculations/loss_breakdown.py sessions/2026-11-27/configs/A_anchors -o anchors_breakdown.csv
```

- The screen shows a summary table, then one `P_remaining(f) = ... -> Eoff = ...` line for each group of points with the same voltage and current step.
- `-o file.csv` also saves the full breakdown with every column, which you can open in Excel or LibreOffice.

### Options you may need

| Option | When to use it |
|---|---|
| `--ipeak scope-pp` | **Default.** Ipeak = scope `AMPL` / 2 (AMPL is peak-to-peak). |
| `--ipeak phase` | Cross-check: Ipeak computed from the phase shift, `Vbus·φ/180/(4·L·f)`. Use it if the scope values look wrong. |
| `--ipeak scope` | Ipeak = scope `AMPL` with no halving (the old behaviour of `TraitementV10.py`). |
| `--params my_circuit.json` | The circuit differs from the 16 Sept bench (another capacitor, other MOSFETs). |

Example `my_circuit.json`. These are the default values; change only the ones that are different:

```json
{
  "r_esr_cap_ohm": 0.125,
  "r_ind_dc_ohm": 0.2,
  "r_mos2_ohm": 0.2059,
  "v_diode_V": 0.845,
  "n_diodes_deadtime": 4
}
```

## 4. Run it on numbers typed in by hand

If you only have the measured values (for example, copied from a notebook), make a CSV file with one row per point:

```csv
group,vbus_V,i_dc_A,ipeak_A,f_kHz,L_uH,td_us,irms_ind_A
A,59.79,0.1329,3.5,50,40,0.3,2.9744
A,59.79,0.1328,3.5,60,40,0.3,2.8731
A,59.79,0.1322,3.5,70,40,0.3,2.7626
```

This example is close to the workbook's 16 Sept inputs, but `i_dc_A` is rounded, so the result will not match step 2 exactly.

```bash
python calculations/loss_breakdown.py points.csv
```

- Rows with the same `group` are fitted together, so you need at least **2 different frequencies** in a group.
- `irms_ind_A` is the inductor RMS current from the scope. Leave it empty and the script uses the workbook's equation (row 46) instead.

## 5. Warnings you may see

| Message | Meaning, and what to do |
|---|---|
| `No fit: need >= 2 frequencies for the same group.` | Each group has only one frequency. Add points or check the `group` column. |
| `WARNING: no scope RMS current for some points; Irms from the equation (row 46).` | The scope did not record an RMS current. The results are still computed, but they are less direct. For the next session, check that `ScopeAutoMeasure` in the config includes `{"type": "RMS", "channel": 2}`. |
| `WARNING: phase shift outside 0..180 deg ...` | Ipeak is probably wrong by a factor of 2. Try `--ipeak scope-pp` or `--ipeak phase`. |
| `ModuleNotFoundError: No module named ...` | The environment is not active, or step 1 was skipped. Activate `.venv` and run `pip install -r requirements.txt`. |
| `ValueError: numpy.dtype size changed` | You are using the system Python. Activate `.venv`. |

## 6. Questions

The open questions about the model (the factor 4 in the dead-time correction, what "I DC condo" means, which scope RMS to use) are listed at the end of [README.md](README.md). Bring them to Luiz or Nicolas, not to the script.
