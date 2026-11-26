# Supervisor dry run, group A_anchors — 2026-11-26T17:30:11

Real `supervisor_script.runner()` on 3 configs, real SPIN (SPOC CUT 5843500300470041) through ThingSet; DMMs, scopes, HV supply and VISA stubbed. Group time 59.7 s.

**3/3 configs ran with every command accepted and read back.**

| config | f (Hz) | commands | phases sent (deg) | mean plateau (s) | run (s) | result |
|---|---|---|---|---|---|---|
| PhaseShift_Voltage_60V_Freq50kHz.json | 50000 | 23 | 3, 0.0, 12.0, 24.0, 36.0, 48.0, 60.0, 72.0, 84.0, 3 | 0.581 | 20.0 | PASS |
| PhaseShift_Voltage_60V_Freq60kHz.json | 60000 | 23 | 3, 0.0, 14.4, 28.8, 43.2, 57.6, 72.0, 86.4, 100.8, 3 | 0.584 | 19.8 | PASS |
| PhaseShift_Voltage_60V_Freq70kHz.json | 70000 | 23 | 3, 0.0, 16.8, 33.6, 50.4, 67.2, 84.0, 100.8, 117.6, 3 | 0.588 | 19.9 | PASS |
