# Bench firmware (SPIN on the Twist 1.4.2), ThingSet

New to it? Start with [GETTING_STARTED.md](GETTING_STARTED.md) (flash, connect, Python example).

The SPIN firmware of the opposition test bench, spoken to by the supervisor over **ThingSet** (`lib/thingset_shield.py`, `"shield_protocol": "thingset"` in the configs). It replaces the string-protocol firmware (`owntech/` on `ReleaseCandidate`, comm protocol `python_twist_comm_protocol#power_tuesday`).

| | |
|---|---|
| Core | [luizvilla/Core](https://github.com/luizvilla/Core) branch `power_tuesday-v2`, commit **`554f8b9a`**: upstream main `8111a0dc` + DMA duty sequences and period-synchronised start/stop + the up-down re-init fix + the ThingSet bench app (from `serial_thingset_example_modular`) + bench patches (GPIO 9 trigger, limits, fractional phase, 10 kHz minimum, dead-time compensation). Old Zephyr (not the 4.4.2 bump). |
| App | `src/` here is a copy of that commit's `src/` (the build uses the core branch's own `src/`). |
| Binary | `bench-thingset-554f8b9a.mcuboot.bin` (env USB, signed for MCUboot), sha256 `be585d93…6de` |
| Shield | Twist 1.4.2 (`board_shield = twist`, `board_shield_version = 1_4_2`) |

## What the bench needs from it

- **ThingSet objects** (shell on the second USB CDC port, interface 2; the first is the console): `Config/Mode`, `Config/Frequency_Hz`, `Config/wDeadTimeComp`, `Config/LegN/{wEnable, wDutyCycle, wPhaseShift, wPhaseShift_deg, wDeadTimeRising_ns, wDeadTimeFalling_ns, wCapa, wDriver, wBuck, wBoost, …}`, `Measurements/*`, `Calibration/*`. Full list: `src/user_data_objects.cpp`.
- **Fractional phase:** `wPhaseShift_deg` (float degrees, 0–360) is rounded to the timer tick (`PowerAPI::setPhaseShiftDeg`, core patch); `wPhaseShift` (whole degrees) still works, both read back the applied value.
- **Scope trigger:** Spin pin 9 (PC7) goes high for 21 control periods (2.1 ms) after each LEG2 phase or duty write.
- **Limits:** phase 0–360°, dead times 100–2000 ns; out-of-range writes are refused (the old value is restored, the shim raises).
- **Frequency:** 10 kHz minimum (`src/app.overlay` overrides the Twist's 50 kHz; timer tick ~2.9 ns), default 50 kHz.
- **Dead-time duty compensation:** `Config/wDeadTimeComp` (off by default): each leg's open-loop duty becomes D − td·f/2 (td = mean of the leg's rising and falling dead times, f the live frequency), recomputed every control period; 0.485 at 100 kHz / 300 ns.

## Build and flash

```sh
git clone git@github.com:luizvilla/Core.git Core-power-tuesday
cd Core-power-tuesday && git checkout 554f8b9a
~/.platformio/penv/bin/pio run -e USB -t upload      # over USB (MCUboot / mcumgr)
```

- Use PlatformIO's own `pio` (`~/.platformio/penv/bin/pio`); the Ubuntu `/usr/bin/pio` fails on Python 3.12.
- After editing `src/app.overlay`, build from clean (`rm -rf .pio/build/<env>`): an incremental build kept the old devicetree.
- With an ST-Link, PlatformIO's newer OpenOCD refuses the adapter ("doesn't support 'hla_swd'"); flash the signed image with the bundled OpenOCD instead:

```sh
PKG=~/.platformio/packages
$PKG/tool-openocd/bin/openocd -s $PKG/tool-openocd/openocd/scripts -f interface/stlink.cfg -f target/stm32g4x.cfg \
  -c "program firmware/bench-thingset-554f8b9a.mcuboot.bin 0x8047800 verify reset exit"
```

The board then enumerates as `OwnTech Technologies TWIST_V1_4_2` (USB 2fe3:0100), two ports: `…-if00` (console, never open it at 1200 baud: it reboots into the bootloader) and `…-if02` (ThingSet).

## Verified

On the SPOC bench (Spin alone, no power stage), `tests/spoc/check_bench_firmware.py`: report in `sessions/2026-11-27/dry-run/firmware-check.md`.
