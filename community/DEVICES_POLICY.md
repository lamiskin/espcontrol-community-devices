# Community Devices Policy

This repository accepts device configurations for **ESP32-S3** and **ESP32-P4** based
touchscreen panels only. Other chip families (ESP32, ESP32-C3, ESP8266, etc.) are not
supported — see upstream issues
[#283](https://github.com/jtenniswood/espcontrol/issues/283) and
[#90](https://github.com/jtenniswood/espcontrol/issues/90) for context.

**Hardware evidence requirement:** Every device submission must include photo or video
proof of hardware-tested operation. Compile-only submissions are accepted as Untested
but will not be marked Working until hardware evidence is provided.

## Vendored `common/` Directory

The repo-root `common/` directory contains byte-identical copies of the few upstream
files that device YAML references with filesystem-relative includes (font glyph lists,
`core_infra.yaml`, `button_widget.yaml`). They exist so end-user ESPHome clones of this
repo can resolve those includes. They are managed exclusively by
`community/scripts/vendor_common.py`; CI verifies they exactly match upstream at the
pinned ref, so hand edits will fail CI. Do not modify them in device PRs.

## Release-asset OTA buffers

Community firmware is served from GitHub Release assets, whose download URLs
302-redirect to a ~950-char signed CDN URL. `esp_http_client`'s default
512-byte header buffers overflow following that redirect
(`HTTP_CLIENT: Out of buffer`), which aborts the OTA before it starts. Every
device's `packages.yaml` must therefore set, in its `# --- community hosting
overrides ---` block, an `http_request:` with `buffer_size_rx` and
`buffer_size_tx` (devices ship `4096`). That block merges with the base
`http_request` in the vendored `common/device/core_infra.yaml` — which cannot
be edited here, hence the per-device override. `community/scripts/check_ota_buffer.py`
enforces this in CI.

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
    - common/**
    - docs/**
    - package.json
    - package-lock.json
    - .gitignore
    - community-pages/**
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
    - components/**
    - src/**

lilygo-jc3248w535:
  allowed:
    - devices/lilygo-jc3248w535/**
    - builds/lilygo-jc3248w535*.yaml
  required:
    - devices/lilygo-jc3248w535/esphome.yaml
    - devices/lilygo-jc3248w535/packages.yaml
    - devices/lilygo-jc3248w535/device/device.yaml
  forbidden:
    - components/**
    - src/**

seeed-esp32-p4-reterminal-d1001:
  allowed:
    - devices/seeed-esp32-p4-reterminal-d1001/**
    - builds/seeed-esp32-p4-reterminal-d1001*.yaml
  required:
    - devices/seeed-esp32-p4-reterminal-d1001/esphome.yaml
    - devices/seeed-esp32-p4-reterminal-d1001/packages.yaml
    - devices/seeed-esp32-p4-reterminal-d1001/device/device.yaml
  forbidden:
    - components/**
    - src/**

seeed-sensecap-indicator-d1:
  allowed:
    - devices/seeed-sensecap-indicator-d1/**
    - builds/seeed-sensecap-indicator-d1*.yaml
  required:
    - devices/seeed-sensecap-indicator-d1/esphome.yaml
    - devices/seeed-sensecap-indicator-d1/packages.yaml
    - devices/seeed-sensecap-indicator-d1/device/device.yaml
  forbidden:
    - components/**
    - src/**

tuya-t3e:
  allowed:
    - devices/tuya-t3e/**
    - builds/tuya-t3e*.yaml
  required:
    - devices/tuya-t3e/esphome.yaml
    - devices/tuya-t3e/packages.yaml
    - devices/tuya-t3e/device/device.yaml
  forbidden:
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
    - components/**
    - src/**

waveshare-esp32-p4-touch-lcd-10:
  allowed:
    - devices/waveshare-esp32-p4-touch-lcd-10/**
    - builds/waveshare-esp32-p4-touch-lcd-10*.yaml
  required:
    - devices/waveshare-esp32-p4-touch-lcd-10/esphome.yaml
    - devices/waveshare-esp32-p4-touch-lcd-10/packages.yaml
    - devices/waveshare-esp32-p4-touch-lcd-10/device/device.yaml
  forbidden:
    - components/**
    - src/**
# --- end policy ---
```
