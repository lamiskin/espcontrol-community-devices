# Community Device Status

| Device | Slug | Status | Last verified | Verified by | Owner | Source |
|--------|------|--------|---------------|-------------|-------|--------|
| Guition JC3248W535 3.5" | guition-esp32-s3-jc3248w535 | Broken | community-v0.0.6-upstream.v2.6.3 | @lamiskin | @lamiskin | [PR #823](https://github.com/jtenniswood/espcontrol/pull/823) |
| Waveshare ESP32-S3-Touch-LCD-4 4" | waveshare-esp32-s3-touch-lcd-4 | Broken | - | - | @codenamefez | [PR #797](https://github.com/jtenniswood/espcontrol/pull/797) |
| Tuya T3E 4" | tuya-t3e | Broken | - | - | @txptr | [PR #660](https://github.com/jtenniswood/espcontrol/pull/660) |
| SenseCAP Indicator D1 4" | seeed-sensecap-indicator-d1 | Working | community-v0.1.2-upstream.v2.6.3 | @mglev1n ([#62](https://github.com/lamiskin/espcontrol-community-devices/issues/62)) | @davidmerrique | [PR #351](https://github.com/jtenniswood/espcontrol/pull/351) |
| Seeed reTerminal D1001 8" | seeed-esp32-p4-reterminal-d1001 | Broken | - | - | @zacs | [PR #885](https://github.com/jtenniswood/espcontrol/pull/885) |
| Waveshare ESP32-P4-WIFI6-Touch-LCD-10.1 10.1" | waveshare-esp32-p4-touch-lcd-10 | Broken | - | - | @sbuchbauer | [Issue #838](https://github.com/jtenniswood/espcontrol/issues/838) |
| Wireless-Tag WT32-SC01 Plus 3.5" | wireless-tag-wt32-sc01-plus | Broken | - | - | @jonnybergdahl | [PR #194](https://github.com/jtenniswood/espcontrol/pull/194) |
| WaveShare ESP32-S3 Smart 86 Box | waveshare-esp32-s3-smart-86-box | Parked | - | - | @salnajjar | [PR #293](https://github.com/jtenniswood/espcontrol/pull/293) |

## Status meanings

- **Working** — compiles at the current pin AND hardware-verified (photo/video evidence).
- **Untested** — compiles at the current pin; awaiting hardware verification. Listed on the installer with a warning badge.
- **Broken** — in the repo but fails to compile at the current pin (nightly build flags this). Omitted from the installer.
- **Graduated** — adopted by upstream; updates handed over to upstream's channel ([graduation plan](https://lamiskin.github.io/espcontrol-community-devices/reference/graduation)). Not in this repo.
- **Parked** — device config is not in the repo (yet): waiting on an upstream dependency, or the original config needs re-submission. Not built, not listed on the installer. Details live in the device's tracking issue or the linked source PR.

## Column meanings

- **Last verified** — the release pin the device was confirmed on. `-` until someone verifies it.
- **Verified by** — who confirmed it on real hardware, with a link to their evidence (issue or PR comment). This is often *not* the porter: the **Owner** column credits whoever contributed the config, and the two are only the same when the porter owns the panel. Both appear on the device's docs page.
- **Source** — the upstream PR or issue the port came from.

### Parked device notes

- **WaveShare ESP32-S3 Smart 86 Box** — the original config from upstream [PR #293](https://github.com/jtenniswood/espcontrol/pull/293) is unrecoverable: the author's fork was deleted and the PR head rewritten before deletion, leaving no diff, and no config was pasted in the thread. The upstream maintainer explicitly welcomed a community version in that thread. Re-submission by a hardware owner is invited — tracked in [issue #15](https://github.com/lamiskin/espcontrol-community-devices/issues/15).
