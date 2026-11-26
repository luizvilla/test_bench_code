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
| 50 | | | 4.089 | |
| 60 | | | 4.272 | |
| 70 | | | 4.437 | |

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
