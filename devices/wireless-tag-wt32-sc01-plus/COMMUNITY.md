# Wireless-Tag WT32-SC01 Plus 3.5" ESP32-S3

- **Chip:** ESP32-S3 on the WT32-S3-WROVER-N16R2 module — 16MB flash, 2MB
  quad PSRAM (vendor datasheet; 16MB is why this device needs no reduced
  factory image, unlike the 8MB `seeed-sensecap-indicator-d1`)
- **Display:** 3.5" 480×320 ST7796 on the 8-bit 8080 parallel bus, landscape
- **Touch:** FT6336 capacitive (I2C, interrupt on GPIO7)
- **Backlight:** LEDC PWM on GPIO45
- **Logging:** UART0 via the onboard CP2102N USB-UART bridge
- **Grid:** 3×2 (6 slots)
- **Upstream PR:** [#194](https://github.com/jtenniswood/espcontrol/pull/194)
- **PR author:** @jonnybergdahl
- **Upstream pin:** v2.8.0

## Provenance

The hardware definition comes from @jonnybergdahl's upstream PR #194, which the
upstream maintainer declined under the own-the-hardware support policy ("by all
means run it as a fork"). The fork that hosted the PR branch,
`jonnybergdahl/espcontrol`, has since been deleted — but GitHub keeps a PR's
head on the *target* repo (`refs/pull/194/head`), so the diff outlived the fork
and the hardware layers were recovered from the patch set still attached to the
PR. The author's standalone `jonnybergdahl/jb_espcontrol`, carrying his May-era
firmware release, is still online as a second reference.

That retention is the difference between this port and a parked one: upstream
PR #293 (WaveShare Smart 86 Box) had its head rewritten before its fork was
deleted, leaving the retained ref pointing at nothing recoverable.

Because the PR predates upstream's display-lifecycle rework and the v2.7.1 and
v2.8.0 breaking changes, the port is built the other way round from a plain
branch revival: the in-repo `guition-esp32-s3-jc3248w535` — same 480×320
landscape geometry, same six-slot grid, already current — is the base, and only
the board-specific layers from PR #194 are grafted onto it. Everything in
`fonts.yaml`, `lvgl.yaml` and `sensors.yaml` is therefore the current contract
rather than the May-era originals, which described a 480×480 nine-slot panel.

## Deviations from PR #194

- **ESP-IDF pin dropped.** The PR pinned esp-idf 5.5.2 with an explicit
  `platform_version`. This build uses the framework defaults for the pinned
  ESPHome release, matching every other device in this repo.
- **`dc_pin` override dropped.** ESPHome's `WT32-SC01-PLUS` model preset now
  sets `dc_pin` to GPIO0 with `ignore_strapping_warning` already applied, so
  the PR's restatement of it is redundant.
- **LVGL buffer 12%, not 25%.** The donor's value is tuned for the current
  firmware's memory pressure on a 480×320 S3. Worth revisiting if a hardware
  owner reports sluggish redraws.
- **API pool 4/3/12, not 2/2/4.** The donor's connection pool reflects later
  upstream tuning for OTA reconnects on low-memory panels.
- **Rotation expressed the in-repo way.** PR #194 offset the rotation mapping
  inside the firmware script (option "180" → LVGL rotation 90). This port keeps
  the donor's identity mapping and carries the same offset in the catalog's
  `rotation.displayOffset`, which upstream applies to the label only. Boot
  orientation and the user-visible labels are unchanged; only where the offset
  lives differs.
- **Battery ADC removed.** The donor reads a LiPo divider on GPIO5. This board
  has no battery gauge, and its GPIO5 is the touch controller's I2C SCL.

## What to watch when verifying

Two things are worth a specific look on first hardware run, neither of them a
known fault:

- **PSRAM headroom.** At 2MB this is the smallest PSRAM budget in the repo —
  the other S3 devices carry 8MB. The constrained settings inherited from the
  donor (one image slot, cover art live updates off) should keep it well
  inside that, but cover art and image cards are where it would show first.
- **Touch axis alignment.** ESPHome's `WT32-SC01-PLUS` preset applies
  `mirror_x` in the panel's MADCTL, and the touchscreen carries no matching
  transform. PR #194 ran this same pairing on real hardware, so it is expected
  to be correct — but a horizontally inverted tap is the symptom if it isn't.

## Verification

Untested in this repo. Three people reported owning this panel on the upstream
PR thread — @tablatronix, @JRTax (who confirmed the PR's firmware worked) and
@hlidotbe — so hardware evidence is more reachable here than on most community
ports. A photo or video of the panel running is all it takes to promote this to
**Working**.
