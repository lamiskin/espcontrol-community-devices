# Community Devices Policy

This repository accepts device configurations for **ESP32-S3** and **ESP32-P4** based
touchscreen panels only. Other chip families (ESP32, ESP32-C3, ESP8266, etc.) are not
supported — see upstream issues
[#283](https://github.com/jtenniswood/espcontrol/issues/283) and
[#90](https://github.com/jtenniswood/espcontrol/issues/90) for context.

**Hardware evidence requirement:** Every device submission must include photo or video
proof of hardware-tested operation. Compile-only submissions are accepted as Untested
but will not be marked Working until hardware evidence is provided.

## Policy Rules

The YAML block below is machine-parsed by `community/scripts/check_policy.py`.
A PR's changed files must each match at least one `allowed` glob from either `_global`
or the device slug(s) touched. If a PR adds a new device, it must also add that slug's
policy block in the same PR. `required` files must exist in the HEAD tree for any PR
that touches that slug. `forbidden` paths cause an unconditional failure if touched.

```yaml
# --- begin policy ---
_global:
  allowed:
    - community/**
    - README.md
    - .github/**
    - LICENSE
    - NOTICE

guition-esp32-s3-jc3248w535:
  allowed:
    - devices/guition-esp32-s3-jc3248w535/**
    - builds/guition-esp32-s3-jc3248w535*.yaml
  required:
    - devices/guition-esp32-s3-jc3248w535/esphome.yaml
    - devices/guition-esp32-s3-jc3248w535/packages.yaml
    - devices/guition-esp32-s3-jc3248w535/device/device.yaml
  forbidden:
    - common/**
    - components/**
    - src/**

waveshare-esp32-s3-touch-lcd-4:
  allowed:
    - devices/waveshare-esp32-s3-touch-lcd-4/**
    - builds/waveshare-esp32-s3-touch-lcd-4*.yaml
  required:
    - devices/waveshare-esp32-s3-touch-lcd-4/esphome.yaml
    - devices/waveshare-esp32-s3-touch-lcd-4/packages.yaml
    - devices/waveshare-esp32-s3-touch-lcd-4/device/device.yaml
  forbidden:
    - common/**
    - components/**
    - src/**
# --- end policy ---
```
