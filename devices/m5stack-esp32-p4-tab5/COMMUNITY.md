# M5Stack Tab5 5" ESP32-P4

- **Chip:** ESP32-P4 (16MB flash, hex PSRAM @ 200MHz)
- **Display:** 5" 1280×720 MIPI-DSI, ST7123, landscape (native 720×1280, rotated)
- **Touch:** ST7123 capacitive (I2C, interrupt GPIO23, reset via IO expander)
- **Network:** ESP32-C6 co-processor over SDIO (`esp32_hosted`)
- **Audio:** ES8388 DAC + ES7210 ADC
- **Battery:** INA226 monitor (`device/battery.yaml`)
- **IO expanders:** two PI4IOE5V6408 (0x43, 0x44) gating LCD/touch reset,
  WiFi power and antenna select, speaker enable and charging
- **Grid:** 6×4 (24 slots) — the densest in this repo
- **Source:** [issue #95](https://github.com/lamiskin/espcontrol-community-devices/issues/95)
  and the author's port at
  [direk/espcontrol_m5stack_tab5](https://github.com/direk/espcontrol_m5stack_tab5)
- **Port author:** @direk
- **Upstream pin:** v2.8.4

## Provenance

Unlike most devices here, this did not come from an unmerged upstream PR. @direk
owns the hardware, wrote a complete EspControl device folder against upstream,
and published it alongside a device request on this repo's tracker. The port was
already on the current firmware contract when it arrived — the display-lifecycle
API (`espcontrol_app.display()`), `display_backlight_handle_state` on the
backlight, and `cover_art_pause_after_touch` on the touch handler were all
present, so no migration was needed.

## Panel revisions

The Tab5 ships with more than one panel, and ESPHome selects it at compile time:

- **v2 (ST7123 panel + ST7123 touch)** — what this build targets, and what @direk
  owns. SKUs C145 and K145 are the same board; K145 is the battery bundle.
- **v2 (ST7121 panel)** — some "v2" units ship this instead. ESPHome distinguishes
  them only by touch controller firmware version at runtime, which a compile-time
  build cannot do. An ST7121 unit needs its own build.
- **v1 (ILI9881C panel + GT911 touch)** — a different stack entirely; would be a
  separate device entry.

If your screen stays blank on this build, that is the likeliest cause.

## Changes from the author's original

- **Pin.** `espcontrol_component_ref` moved from `main` to this repo's pin
  (v2.8.4), so the device tracks a tested upstream release rather than a moving
  target.
- **`api_encryption_dynamic.yaml` dropped.** The original entry point pulled
  `common/addon/api_encryption_dynamic.yaml`, which exists on upstream `main` but
  not at the pinned release. The device's own `api:` block covers what it needs.
- **Remote-include form.** `packages.yaml` was converted from in-tree relative
  includes to this repo's remote-package form, with the community hosting
  overrides (web UI URL, OTA manifest, enlarged `http_request` buffers).
- **API pool override dropped.** The original set `api: max_connections: 5`.
  Neither of this repo's other ESP32-P4 devices overrides the API pool, so the
  Tab5 now takes the shared default from `core_infra.yaml` too.
- **`width_compensation_vertical`.** The generated grid wiring gained this line
  from the catalog's `rotateWidthCompensation`, matching the other rotatable P4
  devices.

## Verification

Untested in this repo. @direk owns the hardware and offered to test — a photo or
video of it running is all it takes to promote this to **Working**.

Worth checking first: whether the 24-slot 6×4 grid is comfortable at 5 inches
(it is the densest grid here, on the smallest P4 panel), and touch accuracy after
the 270° rotation.
