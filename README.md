# espcontrol-community-devices

[![CI](https://github.com/lamiskin/espcontrol-community-devices/actions/workflows/community-ci.yml/badge.svg)](https://github.com/lamiskin/espcontrol-community-devices/actions/workflows/community-ci.yml)
[![Nightly](https://github.com/lamiskin/espcontrol-community-devices/actions/workflows/community-nightly.yml/badge.svg)](https://github.com/lamiskin/espcontrol-community-devices/actions/workflows/community-nightly.yml)
[![Latest release](https://img.shields.io/github/v/release/lamiskin/espcontrol-community-devices?label=release)](https://github.com/lamiskin/espcontrol-community-devices/releases/latest)
[![Docs & installer](https://img.shields.io/badge/docs-installer-0052cc)](https://lamiskin.github.io/espcontrol-community-devices/)

**Unofficial** community-maintained device configurations for
[EspControl](https://github.com/jtenniswood/espcontrol).

This repository is **not** maintained by or affiliated with the upstream project.
It provides additional device support for hardware that upstream has declined to
officially include (upstream only supports panels the maintainer can personally
test — a policy this repo works with, not around).

**📖 Documentation & installer: [lamiskin.github.io/espcontrol-community-devices](https://lamiskin.github.io/espcontrol-community-devices/)**

## Supported devices

See [community/STATUS.md](community/STATUS.md) for the full list and per-device
status. Devices marked **Working** are hardware-verified; **Untested** devices
compile and are flashable but await verification by someone with the hardware —
if that's you, a photo/video of the panel running is all it takes to promote one.

## Install

**Browser (recommended):** open your device's page on the
[docs site](https://lamiskin.github.io/espcontrol-community-devices/),
connect the panel via USB, and click Install. Firmware updates after that are
over-the-air.

**ESPHome dashboard:** after flashing, the device can be adopted in the ESPHome
dashboard like any official EspControl panel — the generated config compiles
as-is. To build manually instead, copy `devices/<slug>/esphome.yaml`, set your
device name and WiFi secrets, and `esphome run` it.

## How it works

This is a thin overlay on upstream, pinned to an upstream release
(`community/upstream-ref.txt`):

- Device configs pull upstream's shared YAML via ESPHome remote packages at the
  pin; the espcontrol components come from upstream's repo the same way.
- The few upstream files that device configs must resolve locally are vendored
  byte-identical under `common/` (checksum-checked in CI against the pin).
- Firmware, the web configurator, and OTA update manifests are built in CI and
  served from this repo's GitHub Pages — devices never depend on upstream's
  hosting.
- Pin bumps arrive as automated PRs that must compile every device before
  merging, so installs only ever reference tested states.

## Contributing

- **New device:** see
  [community/docs/adding-a-device.md](community/docs/adding-a-device.md).
  ESP32-S3/P4 class panels only (see
  [community/DEVICES_POLICY.md](community/DEVICES_POLICY.md)).
- **Request a device:** open a
  [device request](https://github.com/lamiskin/espcontrol-community-devices/issues/new/choose).
- **Own an Untested device?** Flash it from the installer and report — hardware
  verification is the most valuable contribution here.

## License

Licensed under the same terms as upstream — see [LICENSE](LICENSE) and
[NOTICE](NOTICE). Device ports retain credit to their original authors in
[community/STATUS.md](community/STATUS.md).
