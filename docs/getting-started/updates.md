---
title: Updates
description: "How OTA firmware updates work for community EspControl devices, and how community releases track upstream versions."
---

<!--@include: ../parts/warning.md-->

# Updates

## Over-the-air updates

Community panels update the same way official ones do: the panel checks this
project's update feed and offers new firmware in its web configurator and in
Home Assistant (as an ESPHome update entity). No USB cable needed after the
first install.

The update feed lives on this project's hosting — `firmware/<device>/` on this
site — **not** upstream's. Official panels and community panels have entirely
separate update channels; neither will ever offer the other's firmware.

## How releases work

Community releases are tagged like:

```
community-v0.0.8-upstream.v2.6.3
└────┬────┘         └───┬───┘
 community          the upstream EspControl
 release            release it's built from
```

Every release compiles **all** community devices against that pinned upstream
version — a release is only published if every device builds. When upstream
ships a new version, an automated pin-bump proves every community device still
compiles before anything reaches your panel.

This means community updates **lag upstream releases by design** — usually
briefly, sometimes longer if an upstream change breaks a community device and
needs porting work. The nightly build catches breakage early; a device that
stops compiling is marked **Broken** in the
[status table](https://github.com/lamiskin/espcontrol-community-devices/blob/main/community/STATUS.md)
and pulled from the installer until fixed (already-installed panels keep
working — they just won't receive updates until the fix lands).

## If your device graduates to upstream

Should upstream ever adopt a community device officially, its updates hand
over to upstream's channel via a managed OTA transition — see
[Device Graduation](/reference/graduation). You won't need to reflash.

## New features and fixes

Feature development happens upstream — community releases inherit it via pin
bumps. Fixes for device-specific problems (display quirks, touch, pins) happen
here; report them on the
[community issue tracker](https://github.com/lamiskin/espcontrol-community-devices/issues),
never upstream.
