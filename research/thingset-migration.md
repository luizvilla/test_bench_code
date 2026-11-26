# Can the bench firmware and supervisor move to ThingSet?

Research for [#5](https://github.com/luizvilla/test_bench_code/issues/5), input to decision [#6](https://github.com/luizvilla/test_bench_code/issues/6).
Date: 2026-11-26. All claims below were checked against git objects (`git show`/`git log`), not working trees. Nothing in `~/code/Core*` was modified (one detached scratch worktree of `~/code/Core` was used for a test build, see §4).

## TL;DR

- **Luiz is right about the firmware data model.** A ThingSet version of exactly this bench firmware already exists: branch `serial_thingset_example_modular` of OwnTech Core (`github-Core-Luiz`, tip `a5b64146`, 2026-08-01; same commit as local branch in `~/code/Core4`). Its `power_leg_t power_legs[2]` is a flattened, named-field copy of the comm-protocol's `PowerLegSettings power_leg_settings[]`, and every command the supervisor uses has a ThingSet object with a validating callback. This is the "Core4 ThingSet example" that OwnStudio/Theia cites (Theia `docs/architecture.md` row A3, ADR 0019/0021).
- **It merges cleanly onto the target core** `power_tuesday-v2` = `feature/hrtim-dma-sequences` (`34e047bd`): its base `294dfb2f` is an ancestor of `34e047bd`, and `git merge-tree` reports no conflicts. ThingSet itself (`thingset-zephyr-sdk` `e57447bb`, `thingset-node-c` `68c75448`) is already pinned in that core's `west.yml`. Nothing ThingSet-related is missing from the old-Zephyr core. A test build of the merge on that core **succeeds** (Flash 82.1%, RAM 43.1%, §4).
- **What is not done:** (1) the bench-specific parts of `owntech/main.cpp` (scope trigger GPIO pulses on phase/duty change, dead-time 100–2000 ns limits, phase 0–360 range); (2) the **supervisor side**: `supervisor_class.py` calls `Shield_Device.sendCommand(...)` with string actions, and that has to be replaced; (3) **live hardware checks**. The branch's own handoff says the metadata and frequency fixes "have not been exercised live on real hardware yet".
- **The two new commands cost about the same in firmware either way.** Fractional phase needs new firmware math in both cases: the core's `setPhaseShift(leg_t, int16_t)` takes whole degrees only. Dead-time duty compensation is application logic in the control loop. The protocol choice only changes the plumbing around them.
- **Recommendation for 27 Nov:** put the two commands into the **string protocol tonight** (≈2.5–3.5 h, low risk, known-good bench path). Move to ThingSet **after** the session (≈14–20 h), behind a `sendCommand`-compatible shim so `supervisor_class.py` barely changes. A ThingSet-tonight attempt is possible (≈7–10 h), but it puts an unverified transport and an unverified port-selection change on the critical path of a measurement session.

## 1. What exists, and where

| Piece | Location | Commit / state |
|---|---|---|
| Bench firmware (string protocol) | `test_bench_code` `owntech/main.cpp`, `owntech/app.ini` on branch `ReleaseCandidate` | `bc0f9c2`. **Note:** `session-2026-11-27` (lineage `OnlyScripts`) deletes `owntech/` entirely (`f4b9c83`, "excl. µC"); the firmware lives only on `ReleaseCandidate`. |
| String protocol, firmware half | `python_twist_comm_protocol` branch `power_tuesday`, `src/comm_protocol.{h,cpp}`, pulled by `app.ini` `lib_deps` | `175a0d4`. Also sets USB product `COMM-MASTER`, PID `0x0101` (`src/lib.conf`). |
| String protocol, Python half | `comm_protocol/src/Shield_Class.py` (vendored in `session-2026-11-27`) | `sendCommand` maps action strings to e.g. `s_LEG2_p_{value}` |
| Supervisor | `supervisor_class.py`, `supervisor_script.py` on `session-2026-11-27` | uses only `sendCommand` (no `getMeasurement`, no frame parsing) |
| **ThingSet bench firmware (most complete)** | `OwnTech Core` branch `serial_thingset_example_modular` (remote `github-Core-Luiz`, local in `~/code/Core4`): `src/main.cpp`, `src/user_data_objects.{h,cpp}`, `src/thingset_callbacks.cpp`, `src/scope_capture.*`, `src/scope_data_port.*`, `src/app.conf`, `src/app.overlay` | `a5b64146` (2026-08-01), 40 commits on `294dfb2f`; plan + handoff in `THINGSET_COMM_PROTOCOL_PLAN.md` |
| ThingSet bench firmware (earlier, no scope) | `serial_thingset_example` (local in `~/code/Core`) | `ad6d44dc` (2026-07-28), base `e192d529` |
| Python ThingSet clients | (a) `src/tools/thingset_tools.py` (`ThingSetTools`: get/read/write/discover, port probe) + `src/tools/power_test_bench.py` (`PowerTestBench`: `set_mode`, `set_frequency`, `configure_leg`, `read_measurements`, `power_on`, `shutdown`, scope arm/trigger/download, verified writes) on the modular branch; (b) Theia `app/python/ownstudio_lab/thingset.py` (`ThingSet`: get/names/tree/update, 32-byte chunking); (c) `Core2/tests/common/spoc/thingset.py` (test helper) | all are ThingSet **text mode over the Zephyr shell**, pyserial only |
| Older ThingSet work (not relevant tonight) | `v1.0.0-rc1-thingset` (2024-11, Jean; base `a64b7273`, 216 files), `thingset-update` (2024-03, CAN), `serial_thingset_singlephasecode` (2026-07-24, single-phase inverter) | superseded by the modular branch |
| Examples migration | `~/code/examples` branch `thingset_examples` (`THINGSET_COMMUNICATION_MIGRATION_PLAN.md`) | uses Core4 `src` as the reference; conventions differ slightly (`Config/Mode/wMode`) |

Transport details (modular branch `src/app.conf`, `src/app.overlay`, `src/README.md`):
- ThingSet is reached through `CONFIG_OWNTECH_COMMUNICATION_ENABLE_CAN=y`. That is the only Kconfig switch that selects `THINGSET`, so CAN/ISOTP get compiled in too. Then `CONFIG_THINGSET_SHELL=y`, `SHELL_CMDS_SELECT=y`, `LOG=n`.
- The board enumerates **two CDC-ACM interfaces with the same VID/PID**: `if00` = console + scope data, `if02` = ThingSet shell. Host must `select thingset` once per boot and escape `"` in JSON (`=Config/Leg2 {\"wPhaseShift\":30}`).

## 2. Mapping of the current command set

Supervisor call → string wire format (`Shield_Class.py`) → firmware handler (`comm_protocol.cpp`) → ThingSet object (`user_data_objects.cpp`, modular branch) → callback behaviour (`thingset_callbacks.cpp`).

| `sendCommand` | Wire | ThingSet object | 1:1? |
|---|---|---|---|
| `IDLE` / `POWER_OFF` / `POWER_ON` | `d_i` / `d_f` / `d_o` | `/Config/Mode` = 0 / 2 / 1 (uint8, same enum order `IDLE, POWER_ON, POWER_OFF`) | Yes |
| `LEG, LEGn, ON/OFF` | `s_LEGn_l_on` | `/Config/Legn/wEnable` (start/stop in critical task, gated by Mode) | Yes |
| `CAPA, LEGn, ON/OFF` | `s_LEGn_c_on` | `/Config/Legn/wCapa` → `connectCapacitor`/`disconnectCapacitor` | Yes |
| `DRIVER` | `s_LEGn_v_on` | `/Config/Legn/wDriver` → `connectDriver`/`disconnectDriver` | Yes. Both paths call `PowerAPI::disconnectDriver()`, which uses `setPin` in both branches on the target core (`Power.cpp` ~l.663). This is a core issue, not a migration regression. |
| `BUCK` / `BOOST` | `s_LEGn_b_*` / `_t_*` | `/Config/Legn/wBuck`, `wBoost` | Yes |
| `REFERENCE, LEGn, VAR, x` | `s_LEGn_r_V1_x` | `/Config/Legn/wReferenceValue` + `wTrackingVar` (TWIST six channels) | Yes (two fields instead of one command) |
| `DUTY, LEGn, x` | `s_LEGn_d_%.5f` (0–1) | `/Config/Legn/wDutyCycle` (float, restored if out of 0–1) | Yes |
| `FREQUENCY, LEG1, f` | `s_LEG1_f_f` → `spin.pwm.setFrequency` | `/Config/Frequency_Hz` (global, uint32) → `shield.power.setFrequency` | Yes, and arguably better (fixed `5d6e5ae7`; never verified live) |
| `DEAD_TIME_RISING/FALLING, LEGn, ns` | `s_LEGn_x_ns` / `_z_` (limits 100–2000) | `/Config/Legn/wDeadTimeRising_ns`, `wDeadTimeFalling_ns` (uint16) → `setDeadTime` | Field yes; **100–2000 ns limit missing** in the callback |
| `PHASE_SHIFT, LEGn, deg` | `s_LEGn_p_deg` (`atoi`, 0–360, int16) | `/Config/Legn/wPhaseShift` (int16, −360…360) → `setPhaseShift` | Yes, whole degrees only |
| `CALIBRATE` | `k_V1_g_…_o_…` | `/Calibration/<ch>/{wGain,wOffset,wStore}` | Yes |
| frames `frame_POWER_ON/OFF` | pushed text lines | `/Measurements/*` (V/I/T, `rV1Max_V`, `rDuty1/2`), read on demand | Replaced (the supervisor doesn't use frames) |
| scope `_a`/`_r` | toggles | `/Debug/Scope/*` + `D` on `if00` | Replaced; verified live 2026-07-30 |

**Missing from the ThingSet app compared with the bench `main.cpp` (`ReleaseCandidate`):**
1. **Oscilloscope trigger GPIO:** `PHASE_GPIO 9` is pulsed for about 21 critical-task periods when LEG2 phase changes, and `PWM_GPIO 9` when LEG2 duty changes (`main.cpp` l.314–329, 375–389). The bench scopes trigger on this, so it must be ported. About 20 lines.
2. **Dead-time limits** of 100–2000 ns, and phase range 0–360 (the bench rejects negatives).
3. The **USB identity** `COMM-MASTER`/PID `0x0101` comes from the comm-protocol library's `lib.conf`. The supervisor finds the board by `shield_vid`/`shield_pid` (`base-config.json`: 12259/257) and takes `ports[0]`. With ThingSet there are two interfaces on one PID, so it has to select `if02` explicitly (by-id path or the probe in `ThingSetTools.__init__`).
4. **Leg 3 / OwnVerter:** not needed for the bench (TWIST).

## 3. The two new commands

- **Fractional phase (float degrees).** Neither path supports it today. Core API: `PowerAPI::setPhaseShift(leg_t, int16_t)` → `PwmHAL::setPhaseShift` computes `(period * deg) / 360` in integers, then calls `hrtim_phase_shift_set(tu, uint16_t ticks)` (public in `hrtim.h` l.353). The app can do the same computation in float and call `hrtim_phase_shift_set` directly, without changing the core. Watch the `PWMB`/up-down period special cases copied from `PwmHAL.cpp` l.255–275. The firmware work is the same for both protocols.
  - String protocol: change `phaseShiftHandler` (`atoi`→`atof`, `int16_t`→`float`) **in the external library** `python_twist_comm_protocol#power_tuesday`. Either push to that branch or repoint `lib_deps` to a fork branch or path. `Shield_Class.py` already formats `f"..._p_{value}"`, so a float passes through unchanged.
  - ThingSet: add `THINGSET_ADD_ITEM_FLOAT(ID_CONFIG_LEGn, …, "wPhaseShift_deg", …)` with a callback branch. No Python client change (generic `write`).
- **Dead-time duty compensation ON/OFF.** This is application logic in `update_leg_duty` / the bench's duty block. One possible form is `duty ± (dt_rise − dt_fall)·f`; the formula is Luiz's call, and this research didn't verify it. Plus a bool flag. String protocol: a new `power_settings[]` entry (`NUM_OF_SETTINGS` 11→12, a new letter, `boolSettingsHandler` or a new handler) plus a `message_formats` entry. ThingSet: one `THINGSET_ADD_ITEM_BOOL` (`wDtComp`) plus a field in `power_leg_t`.

## 4. Old-Zephyr core: what is missing

- ThingSet modules are already pinned in `west.yml` of `34e047bd` (and of upstream `8111a0dc`). The Kconfig path (`owntech_communication/zephyr/Kconfig`) and `spin.metaData` (`SpinAPI.h` l.107, used by `/Converter`) are present.
- `git merge-tree --write-tree 34e047bd a5b64146` → clean (tree `40a4356a`).
- Test build of that merge (detached scratch worktree, `pio run -e USB`): **SUCCESS** (2026-11-26, toolchain gcc-arm 12.3.1): Flash 82.1% (186,528 / 227,328 B), RAM 43.1%. The firmware is not flashed or run, so this is a compile-level proof only.
- Flash budget: the branch reported 80% after `163b0140` (avoiding `sscanf`/`snprintf`). The DMA-sequence commits add code. Adding the bench's `scopemimicry`/`control_library` deps and keeping `printk` float formatting could push it back up. Re-check after porting.

## 5. Supervisor side

- Which client: use the modular branch's `thingset_tools.py` (`ThingSetTools`), plus `power_test_bench.py` where useful. It is pyserial-only, has unit tests with a fake client, handles `select thingset` and quote escaping, and probes ports. Theia's `ownstudio_lab/thingset.py` is an equivalent, smaller alternative. I did not evaluate the upstream ThingSet Python packages; all OwnTech tooling found uses text mode over the shell.
- Lowest-churn design: add a `ThingSetShield` class with the **same `sendCommand(action, *args, delay=…)` signature**. It maps each action to a single write (`"PHASE_SHIFT","LEG2",v` → `write("Config/Leg2", {"wPhaseShift": v})`). Then `supervisor_class.py` only changes the constructor and port lookup (l.253–258). Writes return `:84`/error codes, so `delay` can drop and errors become exceptions instead of silent `printk` lines.

## 6. Risks for a session tomorrow (if ThingSet were used)

1. **Unverified on hardware:** the frequency write path (`5d6e5ae7`) and metadata rework were build-only. Frequency is a swept bench parameter.
2. **Port selection:** two CDC ports share VID/PID, and `find_devices`+`ports[0]` can pick the console. Opening `if00` at 1200 baud triggers the bootloader (README warning).
3. **Shell quirks:** quote escaping and long requests. Theia chunks to 32 bytes because the RX ring is small, and keeps the shell buffer at 256.
4. **Missing scope-trigger GPIO pulse.** Without it, the existing oscilloscope capture flow breaks silently.
5. **Missing dead-time bounds:** a typo writes, for example, 30 ns straight to the HRTIM.
6. **Timing:** request/response per write (plus readback if using `PowerTestBench`). Sweeps get slower per step but deterministic; no measured numbers.
7. **Flash headroom** on the DMA-sequences core with all bench deps: unknown until built.
8. **Two moving parts at once:** the new core `power_tuesday-v2` and the new transport. If something misbehaves you cannot tell which change caused it.

## 7. Effort estimates

(a) **Tonight, minimal: string protocol + two commands**, ≈ **2.5–3.5 h**
- library `comm_protocol.cpp/.h`: float phase handler + DT-comp flag command, push to the `power_tuesday` branch or a fork branch referenced in `app.ini`: 1 h
- `main.cpp`: float phase→ticks via `hrtim_phase_shift_set`, DT compensation in the duty block: 0.5–1 h
- `Shield_Class.py` `message_formats` entry, supervisor config knob: 0.25 h
- build on `power_tuesday-v2` + bench smoke test (phase on scope, comp on/off visible in duty): 0.75–1 h

(a′) **Tonight, ThingSet instead**, ≈ **7–10 h**: port the bench specifics onto the modular branch (GPIO pulses, limits, two new objects) 2–3 h, `ThingSetShield` shim + port selection 1.5–2 h, build/flash/live acceptance of mode/frequency/phase/dead-time/capa/driver + scope trigger 3–4 h, buffer 1 h. Not recommended the night before a campaign.

(b) **Full migration, after the session**, ≈ **14–20 h** (2–3 working days)
- firmware: merge modular branch onto `power_tuesday-v2`, port bench specifics + two new commands, limits, flash check: 4–5 h
- supervisor: `ThingSetShield` shim, port by-id config in `base-config.json`, verified writes, optional `PowerTestBench`, retire `comm_protocol` lib_dep: 3–4 h
- tests: fake-client unit tests for the shim (pattern exists in `src/tools/tests/`): 2–3 h
- hardware acceptance on the bench (the branch's own pending live checks + full sweep A/B against the string-protocol firmware for identical PWM): 4–6 h
- docs (`owntech/README.md` successor, bench README): 1–2 h

## 8. Answer to "is the step simpler than it seems?"

On the **firmware data model, yes**: the objects exist and match, the code merges cleanly onto the target core, and ThingSet is already in its manifest. On **getting the bench onto it, not quite**. The real work is the supervisor transport swap, USB port identity, the bench-only GPIO trigger and limits, and live verification of paths that were only built, not run. That is a day or more of work, not an evening. It fits well after 27 Nov. The two new commands do not get cheaper by going through ThingSet first.
