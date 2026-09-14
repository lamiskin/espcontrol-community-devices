# M5Stack Tab5 5" ESP32-P4 (V1)

- **Chip:** ESP32-P4 (16MB flash, hex PSRAM @ 200MHz)
- **Display:** 5" 1280×720 MIPI-DSI, ILI9881C, landscape (native 720×1280, rotated)
- **Touch:** GT911 capacitive (I2C, interrupt GPIO23, reset via IO expander)
- **Network:** ESP32-C6 co-processor over SDIO (`esp32_hosted`)
- **Audio:** ES8388 DAC + ES7210 ADC
- **Battery:** INA226 monitor (`device/battery.yaml`)
- **IO expanders:** two PI4IOE5V6408 (0x43, 0x44) gating LCD/touch reset,
  WiFi power and antenna select, speaker enable and charging
- **Grid:** 6×4 (24 slots)
- **Source:** [PR #136](https://github.com/lamiskin/espcontrol-community-devices/pull/136)
- **Port author:** @persuader72
- **Upstream pin:** v2.9.0

## Provenance

This is a variant of [`m5stack-esp32-p4-tab5`](../m5stack-esp32-p4-tab5/COMMUNITY.md)
covering the **earlier V1 revision** of the M5Stack Tab5 board. The V1 panel is a
different display and touch stack (ILI9881C + GT911) from the V2 board that the
original device entry targets (ST7123 + ST7123), so it cannot be selected at
runtime — ESPHome binds both at compile time, which is why it needs its own
device entry rather than a flag on the existing one.

@persuader72 owns V1 hardware and adapted the existing V2 device folder, keeping
everything that is genuinely shared (LVGL layout, fonts, sensors, grid geometry,
catalog profile) and changing only what the older board needs.

## Changes from `m5stack-esp32-p4-tab5`

- **Touch controller.** `st7123` → `gt911`, with explicit `calibration`
  (720×1280 native extents) and `interrupt_pin: GPIO23` driving interrupt-based
  updates. The screensaver/cover-art `on_touch` handler is carried over
  unchanged. Four-corner tracking verified on author hardware without an
  explicit `transform`.
- **Display panel.** `model: M5STACK-TAB5-ST7123` → `model: M5Stack-Tab5` with
  explicit `dimensions` (720×1280), selecting the ILI9881C panel.
- **Extra power-rail switches.** V1 exposes three additional IO-expander rails
  not wired on the V2 entry: `speaker_enable`, `usb_5v_power` and
  `external_5v_power`, all defaulting to off.
- **Battery charge defaults.** `battery_charge_enable` and
  `battery_quick_charge_enable` both use `restore_mode: ALWAYS_OFF`
  (V2 uses `ALWAYS_ON`). See Known quirks.

Everything else — `device/lvgl.yaml`, `device/fonts.yaml`, `device/sensors.yaml`,
the catalog profile and the grid geometry — is identical to the V2 device and
should be kept in sync with it when that device changes.

## Panel revisions

The Tab5 ships with more than one panel, and ESPHome selects it at compile time:

- **v1 (ILI9881C panel + GT911 touch)** — what *this* build targets.
- **v2 (ST7123 panel + ST7123 touch)** — covered by
  [`m5stack-esp32-p4-tab5`](../m5stack-esp32-p4-tab5/COMMUNITY.md). SKUs C145 and
  K145 are the same board; K145 is the battery bundle.
- **v2 (ST7121 panel)** — some "v2" units ship this instead. ESPHome distinguishes
  them only by touch controller firmware version at runtime, which a compile-time
  build cannot do. An ST7121 unit needs its own build.

If your screen stays blank on this build, check that you are on a V1 board and
not one of the V2 variants above.

## Known quirks

- **Charging left off at boot.** On the author's V1 board, enabling
  `battery_charge_enable` makes the panel run hot near the USB-C / IP2326.
  Both charge and quick-charge default to off; toggle **Battery Charge Enable**
  (and Quick Charge if you want higher current) when you intentionally charge.
  Not yet confirmed whether this affects all V1 units.
- **Quick-charge pin is board-level.** Tab5 `nCHG_QC_EN` drives a discrete
  MOSFET, not an IP2326 pin. The IP2326 only has `EN` (wired to `CHG_EN`);
  DP/DM fast-charge negotiation only runs while `EN` is high. Leaving QC
  asserted while charge is off is therefore safe for the IC, but we still
  default QC off to match M5Unified's charge-disable path.

## Verification

@persuader72 compiled and flashed this on real V1 hardware (photo on
[PR #136](https://github.com/lamiskin/espcontrol-community-devices/pull/136)).
GT911 touch was checked in all four corners after the 270° landscape rotation
and tracks correctly with the existing `calibration` (no explicit `transform`
needed on this unit). Repo status can be promoted once a release pin that
ships this device is confirmed.
