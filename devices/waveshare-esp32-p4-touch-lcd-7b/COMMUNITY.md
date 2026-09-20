# Waveshare ESP32-P4-WIFI6-Touch-LCD-7B (7")

7-inch 1024x600 IPS touchscreen panel running EspControl for Home Assistant. A
fixed 3x5 grid of 15 configurable buttons controls lights, switches, fans and
other entities with one tap; the panel also shows a clock, indoor/outdoor
temperature and a screensaver with adjustable brightness.

After the initial install everything is configured from the panel's built-in
web page — no YAML editing.

## Hardware

| | |
|---|---|
| SoC | ESP32-P4 (dual RISC-V @360MHz) + ESP32-C6 hosted WiFi 6 over SDIO |
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

**Working** — confirmed on real hardware by @bassrock at
`community-v0.11.0-upstream.v2.10.0` (ESPHome 2026.9.0, espcontrol v2.10.0):
boots, touch works, and the card grid renders live Home Assistant data.

## Quick links

- **Full documentation:** [jtenniswood.github.io/espcontrol](https://jtenniswood.github.io/espcontrol/)
- **Install guide:** [jtenniswood.github.io/espcontrol/install](https://jtenniswood.github.io/espcontrol/install)
