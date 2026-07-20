---
title: EspControl Community Devices
titleTemplate: :title
description: "Unofficial community-maintained EspControl firmware for ESP32 touchscreen panels not officially supported by the upstream project."
---

<!--@include: ./parts/warning.md-->

# EspControl Community Devices

**Community-maintained [EspControl](https://jtenniswood.github.io/espcontrol/) firmware for panels the upstream project doesn't support.**

Upstream EspControl only supports touchscreens its maintainer can personally
test — a sensible policy that keeps official quality high, but one that leaves
out plenty of capable hardware. This project fills that gap: the same
EspControl experience, built from the same upstream code at a pinned release,
for community-contributed panels.

Start here: **[Install](/getting-started/install)** — or jump straight to your
device in the sidebar.

## Supported Devices

<!--@include: ./parts/device-table.md-->

The live build/verification state for every device is in the
[status table](https://github.com/lamiskin/espcontrol-community-devices/blob/main/community/STATUS.md).
**Working** devices are hardware-verified. **Untested** devices compile and are
flashable, but nobody has confirmed them on real hardware yet — if you own one,
[flashing it and reporting back](/reference/support-policy#hardware-verification)
is the single most valuable contribution you can make.

## Which Firmware Do I Need?

- **Your panel is on this site's device list** → install from **this site
  only**. Community firmware is published exclusively here.
- **Your panel is on the
  [upstream supported list](https://jtenniswood.github.io/espcontrol/)**
  (JC8012P4A1, JC1060P470, JC4880P443, ESP32-P4 86 Panel, 4848S040) → install
  from the
  [upstream installer](https://jtenniswood.github.io/espcontrol/getting-started/install)
  **only**. This repo never publishes firmware for officially supported panels,
  and community firmware must never be flashed onto them.

## What EspControl Does

Everything about *using* EspControl — cards, subpages, scenes, sensors, media,
climate, configuration, Home Assistant setup — is identical on community
devices and documented once, upstream:

- [EspControl overview](https://jtenniswood.github.io/espcontrol/)
- [Card types](https://jtenniswood.github.io/espcontrol/card-types/)
- [Configuring the panel](https://jtenniswood.github.io/espcontrol/features/setup)
- [Enable Home Assistant actions](https://jtenniswood.github.io/espcontrol/getting-started/home-assistant-actions)

This site only documents what's *different*: which devices exist, how to
install and update them, and how community support works.

## How This Project Works

- Device configs build against a **pinned upstream release** (currently shown
  in each [release](https://github.com/lamiskin/espcontrol-community-devices/releases)
  tag, e.g. `-upstream.v2.6.3`). Pin bumps must compile every device before
  merging.
- Firmware, OTA updates, and the panel web configurator are built in CI and
  served from this site — community devices never depend on upstream's hosting.
- If upstream ever adopts one of these devices, it
  [graduates](/reference/graduation) with a managed OTA handover.

**Source code and issues:**
[github.com/lamiskin/espcontrol-community-devices](https://github.com/lamiskin/espcontrol-community-devices)
