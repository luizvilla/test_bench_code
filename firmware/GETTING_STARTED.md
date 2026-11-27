# Getting started: the bench firmware on your own SPIN

This is how to run the opposition test bench firmware on a SPIN + Twist and talk to it over ThingSet from Python or MATLAB. [README.md](README.md) has the full firmware details; [src/README.md](src/README.md) lists every ThingSet object.

## 1. What you need

- A SPIN on a **Twist 1.4.2**. For another Twist version, build from source (step 2b) with your `board_shield_version`.
- Python 3 with `pyserial` (`pip install pyserial`), or MATLAB.
- For building: PlatformIO. Use its own `~/.platformio/penv/bin/pio`; the Ubuntu `/usr/bin/pio` fails on Python 3.12.

## 2. Flash the firmware

The firmware is **not** on OwnTech Core main. It is commit `554f8b9a` of [luizvilla/Core](https://github.com/luizvilla/Core) (branch `power_tuesday-v2`), which adds the core patches the app needs (fractional phase, 10 kHz minimum, dead-time compensation, scope trigger on pin 9). Upstream Core will not build it.

**a. Same hardware: flash the prebuilt binary** [bench-thingset-554f8b9a.mcuboot.bin](bench-thingset-554f8b9a.mcuboot.bin) with an ST-Link:

```sh
PKG=~/.platformio/packages
$PKG/tool-openocd/bin/openocd -s $PKG/tool-openocd/openocd/scripts \
  -f interface/stlink.cfg -f target/stm32g4x.cfg \
  -c "program firmware/bench-thingset-554f8b9a.mcuboot.bin 0x8047800 verify reset exit"
```

**b. Build from source** (over USB, no ST-Link needed):

```sh
git clone git@github.com:luizvilla/Core.git && cd Core && git checkout 554f8b9a
~/.platformio/penv/bin/pio run -e USB -t upload
```

With several OwnTech boards plugged in, set `board_id` in `platformio.ini` to the target board's USB serial first.

## 3. Find the ports

The board shows up as two serial ports:

| Port | Use |
|---|---|
| `/dev/serial/by-id/usb-OwnTech_Technologies_…-if02` | **ThingSet shell**: all configuration and measurements |
| `/dev/serial/by-id/usb-OwnTech_Technologies_…-if00` | Console and scope data download |

> **Never open `if00` at 1200 baud**: that reboots the board into the bootloader. Use 115200.

## 4. Talk to it from Python

Use the clients in [src/tools/](src/tools/) **from this repository**: they know the bench-only objects (`phase_shift_deg`, dead-time compensation); the copy in the Core fork does not.

```python
import sys
sys.path.insert(0, "firmware/src/tools")
from thingset_tools import ThingSetTools
from power_test_bench import PowerTestBench

port = "/dev/serial/by-id/usb-OwnTech_Technologies_..._if02"   # your board
with ThingSetTools(port) as ts:
    ts.discover()
    bench = PowerTestBench(ts)

    bench.shutdown()                          # POWER_OFF, both legs disabled
    bench.set_frequency(50_000)               # 10 kHz minimum
    bench.configure_leg(1, duty_cycle=0.5, dead_time_rising_ns=300,
                        dead_time_falling_ns=300)
    bench.configure_leg(2, duty_cycle=0.5, phase_shift_deg=179.5)
    bench.set_dead_time_compensation(True)    # duty becomes D - td*f/2
    print(bench.read_leg(2))
    print(bench.read_measurements())

    # Only on a prepared, current-limited power bench:
    # try:
    #     bench.power_on(1, connect_driver=True, duty_cycle=0.5)
    # finally:
    #     bench.shutdown(disconnect_hardware=True)
```

Every write is read back; a value the firmware refuses raises `PowerTestBenchError`. For a quick check without writing code:

```sh
cd firmware/src/tools
python3 thingset_example.py --port /dev/serial/by-id/...-if02   # reads, stays powered off
```

MATLAB has the same API in camelCase (`configureLeg(2, struct("phaseShiftDeg", 179.5))`, `setDeadTimeCompensation(true)`); see [src/README.md](src/README.md).

## 5. Or from a serial terminal

Open `if02` at 115200 baud, then:

```text
select thingset
?Config null
?Measurements
=Config/Leg2 {\"wPhaseShift_deg\":179.5}
=Config {\"wDeadTimeComp\":true}
```

Quotes must be escaped as shown (the shell strips bare `"`). `:84` means the write was accepted, but the firmware silently restores out-of-range values, so read the value back.

## 6. Limits and safety

- Phase: 0 to 360° (negative values are refused). Dead times: 100 to 2000 ns. Frequency: 10 kHz minimum.
- Writes to the capacitor, driver, phase, dead-time, frequency and calibration objects act **immediately**, even with the converter in `POWER_OFF`. Use an isolated, current-limited setup.
- Scope pin: SPIN pin 9 (PC7) goes high for about 2.1 ms after each LEG2 phase or duty write, for triggering an oscilloscope.

## 7. Running the campaign scripts

To run this repository's `supervisor_script.py` against your board, set `"shield_protocol": "thingset"` in the config (and optionally `"shield_port"`); the transport is [lib/thingset_shield.py](../lib/thingset_shield.py). See the top-level [readme.md](../readme.md).
