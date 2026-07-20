---
title: Install
description: "Install community EspControl firmware from your browser, connect the panel to WiFi, and add it to Home Assistant."
---

<!--@include: ../parts/warning.md-->

# Install

Installing a community device works exactly like installing official
EspControl — flash from the browser, join WiFi, adopt in Home Assistant. The
only difference is **where the firmware comes from**.

::: warning Use the right firmware source
Firmware on this site is **only** for the community devices listed in the
sidebar. If your panel is on the
[upstream supported list](https://jtenniswood.github.io/espcontrol/), use the
[upstream installer](https://jtenniswood.github.io/espcontrol/getting-started/install)
instead — official panels are never published here, and community builds must
never be flashed onto them.
:::

## 1. Flash from the browser

1. Open your device's page from the sidebar and check its status — **Working**
   devices are hardware-verified, **Untested** devices compile but await
   verification.
2. Connect the panel to your computer with a **USB-C data cable** (not a
   charge-only cable).
3. Click the **Install community firmware** button on the device page, using
   **Chrome or Edge** on desktop (WebSerial is required).
4. Pick the serial port when prompted and let the flash finish.

## 2. WiFi, Home Assistant, and panel setup

From here the flow is identical to official EspControl, and upstream's guide
covers it step by step — connect to the panel's setup hotspot, join your
**2.4 GHz** WiFi, add the discovered ESPHome device in Home Assistant, and
allow Home Assistant actions:

- [Upstream install walkthrough](https://jtenniswood.github.io/espcontrol/getting-started/install)
  (start from the WiFi step)
- [Enable Home Assistant actions](https://jtenniswood.github.io/espcontrol/getting-started/home-assistant-actions)
- [Configure cards and pages](https://jtenniswood.github.io/espcontrol/features/setup)

The panel's built-in web configurator is served from this project's hosting,
so it keeps working regardless of upstream.

## ESPHome dashboard / manual builds

After flashing, the panel can be **adopted in the ESPHome dashboard** like any
EspControl device — the generated config references this repo and compiles
as-is.

To build manually instead, each device page has a ready-to-use ESPHome snippet.
The pattern:

```yaml
substitutions:
  name: "your-device-name"
  friendly_name: "Your Device Name"

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

packages:
  setup:
    url: https://github.com/lamiskin/espcontrol-community-devices/
    file: devices/<device-slug>/packages.yaml
    refresh: 1s
```

## Next: staying up to date

See [Updates](/getting-started/updates) for how OTA updates work on community
devices and how releases relate to upstream versions.
