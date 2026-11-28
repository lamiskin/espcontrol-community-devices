# Waveshare ESP32-P4-WIFI6-Touch-LCD-7B (7", ESP32-P4 rev3)

7-inch 1024x600 IPS touchscreen panel running EspControl for Home Assistant. A
fixed 3x5 grid of 15 configurable buttons controls lights, switches, fans and
other entities with one tap; the panel also shows a clock, indoor/outdoor
temperature and a screensaver with adjustable brightness.

After the initial install everything is configured from the panel's built-in
web page — no YAML editing.

## Hardware

| | |
|---|---|
| SoC | ESP32-P4 rev3.x (dual RISC-V @360MHz) + ESP32-C6 hosted WiFi 6 over SDIO |
| Memory | 32MB in-package PSRAM, 32MB external NOR flash |
| Display | EK79007, 1024x600 IPS, 2-lane MIPI-DSI, 52MHz pclk, 1Gbps/lane |
| Touch | GT911 capacitive, 5-point, I2C 0x5D — **no INT, no RST wired** |
| Backlight | GPIO32, **active low**, 5kHz LEDC |
| LCD reset | GPIO33 |
| I2C | SDA GPIO7 / SCL GPIO8 |
| Power | 5V via USB-C (~600mA) |

All values are taken from the vendor BSP at
[waveshareteam/ESP32-P4-WIFI6-Touch-LCD-7B](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-7B),
`examples/arduino/libraries/displays/displays_config.h`.

## Silicon revisions

Waveshare ships this board with two incompatible ESP32-P4 silicon families:
pre-v3 (`chip revision: v1.x`) and rev3 (`v3.0` or newer). A firmware image
built for one family cannot boot the other. This directory is the **rev3**
variant and sets `engineering_sample: false`; the pre-v3 variant and its
install entry are in `devices/waveshare-esp32-p4-touch-lcd-7b`.

Check the first serial line at 115200 (`boot: chip revision: vX.Y`) or run
`python -m esptool --chip esp32p4 -p <port> chip-id` before flashing. A rev3
board (`v3.0` or newer) must use this variant; a pre-v3 board must use the
pre-v3 variant. Do not use `--force` to bypass the bootloader's revision check.

## Notes for this port

- **The panel is declared as `model: CUSTOM`.** ESPHome's `mipi_dsi` component
  ships no EK79007 profile (`models/waveshare.py` has only P4-NANO-10.1, 3.4C
  and 4C), so the timings and the vendor register block are inlined in
  `device/device.yaml`. If ESPHome later adds an EK79007 model, this can be
  replaced with a one-line `model:`.
- **The backlight is active low.** The LEDC pin is declared `inverted: true`.
  Without that the panel is dark at 100% brightness and bright at 0%.
- **No Ethernet.** Unlike the Guition panel this config descends from, the 7B
  has WiFi only, so the dual-transport build path has been removed.
- **Rotation is identity-mapped.** EK79007 is natively upright at 1024x600, so
  selecting `0` applies `0`. (The Guition config offsets by 180 because that
  panel is mounted inverted.) If your unit comes up upside down, change the
  rotation select to `180` in the web UI — no reflash needed.

## Status

**Untested** — this rev3 variant compiles and is ready for hardware
verification, but it has not yet been confirmed on a rev3 board. The pre-v3
variant was confirmed by @bassrock at
`community-v0.11.0-upstream.v2.10.0` (ESPHome 2026.9.0, espcontrol v2.10.0).

See [issue #239](https://github.com/lamiskin/espcontrol-community-devices/issues/239)
for the report that identified the two silicon families.

## Quick links

- **Full documentation:** [jtenniswood.github.io/espcontrol](https://jtenniswood.github.io/espcontrol/)
- **Install guide:** [jtenniswood.github.io/espcontrol/install](https://jtenniswood.github.io/espcontrol/install)
