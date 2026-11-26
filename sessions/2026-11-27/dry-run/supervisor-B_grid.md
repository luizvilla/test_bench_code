# Supervisor dry run, group B_grid — 2026-11-26T17:37:55

Real `supervisor_script.runner()` on 23 configs, real SPIN (SPOC CUT 5843500300470041) through ThingSet; DMMs, scopes, HV supply and VISA stubbed. Group time 462.5 s.

**23/23 configs ran with every command accepted and read back.**

| config | f (Hz) | commands | phases sent (deg) | mean plateau (s) | run (s) | result |
|---|---|---|---|---|---|---|
| PhaseShift_Voltage_60V_Freq100kHz.json | 100000 | 23 | 3, 0.0, 24.0, 48.0, 72.0, 96.0, 120.0, 144.0, 168.0, 3 | 0.609 | 20.9 | PASS |
| PhaseShift_Voltage_60V_Freq10kHz.json | 10000 | 23 | 3, 0.0, 2.4, 4.8, 7.2, 9.6, 12.0, 14.4, 16.8, 3 | 0.575 | 20.2 | PASS |
| PhaseShift_Voltage_60V_Freq11kHz.json | 11000 | 23 | 3, 0.0, 2.64, 5.28, 7.92, 10.56, 13.2, 15.84, 18.48, 3 | 0.575 | 19.6 | PASS |
| PhaseShift_Voltage_60V_Freq12kHz.json | 12000 | 23 | 3, 0.0, 2.88, 5.76, 8.64, 11.52, 14.4, 17.28, 20.16, 3 | 0.573 | 19.5 | PASS |
| PhaseShift_Voltage_60V_Freq14kHz.json | 14000 | 23 | 3, 0.0, 3.36, 6.72, 10.08, 13.44, 16.8, 20.16, 23.52, 3 | 0.574 | 19.6 | PASS |
| PhaseShift_Voltage_60V_Freq15kHz.json | 15000 | 23 | 3, 0.0, 3.6, 7.2, 10.8, 14.4, 18.0, 21.6, 25.2, 3 | 0.574 | 19.7 | PASS |
| PhaseShift_Voltage_60V_Freq16kHz.json | 16000 | 23 | 3, 0.0, 3.84, 7.68, 11.52, 15.36, 19.2, 23.04, 26.88, 3 | 0.575 | 20.4 | PASS |
| PhaseShift_Voltage_60V_Freq18kHz.json | 18000 | 23 | 3, 0.0, 4.32, 8.64, 12.96, 17.28, 21.6, 25.92, 30.24, 3 | 0.575 | 19.5 | PASS |
| PhaseShift_Voltage_60V_Freq20kHz.json | 20000 | 23 | 3, 0.0, 4.8, 9.6, 14.4, 19.2, 24.0, 28.8, 33.6, 3 | 0.577 | 20.1 | PASS |
| PhaseShift_Voltage_60V_Freq22kHz.json | 22000 | 23 | 3, 0.0, 5.28, 10.56, 15.84, 21.12, 26.4, 31.68, 36.96, 3 | 0.577 | 20.6 | PASS |
| PhaseShift_Voltage_60V_Freq25kHz.json | 25000 | 23 | 3, 0.0, 6.0, 12.0, 18.0, 24.0, 30.0, 36.0, 42.0, 3 | 0.575 | 19.6 | PASS |
| PhaseShift_Voltage_60V_Freq27kHz.json | 27000 | 23 | 3, 0.0, 6.48, 12.96, 19.44, 25.92, 32.4, 38.88, 45.36, 3 | 0.577 | 19.7 | PASS |
| PhaseShift_Voltage_60V_Freq30kHz.json | 30000 | 23 | 3, 0.0, 7.2, 14.4, 21.6, 28.8, 36.0, 43.2, 50.4, 3 | 0.577 | 19.7 | PASS |
| PhaseShift_Voltage_60V_Freq33kHz.json | 33000 | 23 | 3, 0.0, 7.92, 15.84, 23.76, 31.68, 39.6, 47.52, 55.44, 3 | 0.578 | 20.3 | PASS |
| PhaseShift_Voltage_60V_Freq37kHz.json | 37000 | 23 | 3, 0.0, 8.88, 17.76, 26.64, 35.52, 44.4, 53.28, 62.16, 3 | 0.582 | 20.1 | PASS |
| PhaseShift_Voltage_60V_Freq41kHz.json | 41000 | 23 | 3, 0.0, 9.84, 19.68, 29.52, 39.36, 49.2, 59.04, 68.88, 3 | 0.581 | 22.2 | PASS |
| PhaseShift_Voltage_60V_Freq45kHz.json | 45000 | 23 | 3, 0.0, 10.8, 21.6, 32.4, 43.2, 54.0, 64.8, 75.6, 3 | 0.582 | 20.0 | PASS |
| PhaseShift_Voltage_60V_Freq55kHz.json | 55000 | 23 | 3, 0.0, 13.2, 26.4, 39.6, 52.8, 66.0, 79.2, 92.4, 3 | 0.582 | 19.7 | PASS |
| PhaseShift_Voltage_60V_Freq61kHz.json | 61000 | 23 | 3, 0.0, 14.64, 29.28, 43.92, 58.56, 73.2, 87.84, 102.48, 3 | 0.584 | 19.8 | PASS |
| PhaseShift_Voltage_60V_Freq67kHz.json | 67000 | 23 | 3, 0.0, 16.08, 32.16, 48.24, 64.32, 80.4, 96.48, 112.56, 3 | 0.589 | 20.4 | PASS |
| PhaseShift_Voltage_60V_Freq74kHz.json | 74000 | 23 | 3, 0.0, 17.76, 35.52, 53.28, 71.04, 88.8, 106.56, 124.32, 3 | 0.591 | 20.5 | PASS |
| PhaseShift_Voltage_60V_Freq82kHz.json | 82000 | 23 | 3, 0.0, 19.68, 39.36, 59.04, 78.72, 98.4, 118.08, 137.76, 3 | 0.595 | 20.0 | PASS |
| PhaseShift_Voltage_60V_Freq90kHz.json | 90000 | 23 | 3, 0.0, 21.6, 43.2, 64.8, 86.4, 108.0, 129.6, 151.2, 3 | 0.601 | 20.2 | PASS |
