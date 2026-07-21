# Contributing

Thanks for helping with community EspControl devices! This is an unofficial
project — please keep all activity here and never on the upstream EspControl
repo.

## The most valuable contribution: hardware verification

Most devices here are compile-tested but **Untested** on real hardware. If you
own one, flash it from the
[installer](https://lamiskin.github.io/espcontrol-community-devices/) and
report back (a photo or short video of the panel running) — that promotes it
to **Working**. See the
[support policy](https://lamiskin.github.io/espcontrol-community-devices/reference/support-policy#hardware-verification).

## Adding a device

Full walkthrough:
[community/docs/adding-a-device.md](../community/docs/adding-a-device.md).

In short: ESP32-S3 / ESP32-P4 panels only (see
[DEVICES_POLICY.md](../community/DEVICES_POLICY.md)), each device builds against
upstream at the pinned release, and CI must compile it before merge. Hardware
evidence is required to mark a device Working.

## Reporting a problem

Use the **Bug report** issue form — its *Which device?* dropdown auto-labels
the issue. For how EspControl itself works (cards, configuration, Home
Assistant), see the [upstream docs](https://jtenniswood.github.io/espcontrol/).

## Requesting a device

Open a **Device request** issue. Note that a device can only be supported if
someone with the hardware can build and verify it.

## Ground rules

- Never file community-device issues on the upstream repo.
- Don't edit generated files by hand (docs pages, device labels, vendored
  `common/`) — CI regenerates and verifies them.
- Be respectful; see the [Code of Conduct](CODE_OF_CONDUCT.md).
