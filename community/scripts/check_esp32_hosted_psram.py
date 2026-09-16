#!/usr/bin/env python3
"""
check_esp32_hosted_psram.py – Enforce that every ESP32-P4 device keeps its
ESP32-C6 hosted-WiFi transport buffer pool in PSRAM.

Why this exists
----------------
ESP-Hosted preallocates a DMA transport buffer pool before ESPHome starts.
On P4 display builds that pool can fail to fit in internal RAM ("HS_MP:
mempool create failed: no mem"), aborting OTA. The fix reached for here was
CONFIG_ESP_HOSTED_USE_MEMPOOL: "n" — disable the pool entirely, fall back to
dynamic buffers. That avoids the boot failure, but leaves inbound Home
Assistant API/web requests dependent on dynamic buffer allocation, which can
silently starve under load and never recover
(jtenniswood/espcontrol#1099) — a WiFi/API disconnect with no crash and no
log line pointing at the cause.

Upstream's real fix (PR #1105) keeps the pool but relocates it to PSRAM
instead: esp32_hosted: { use_psram: true }. That solves the original boot
failure *and* avoids the dynamic-allocation starvation bug, so it is a
strict improvement over "n" — every device that configures esp32_hosted
must set it.

We didn't catch that upstream's fix had never been adopted here because our
fleet-parity check (check_wiring_parity.py) compares each P4 device against
one upstream reference device, and that reference — like six of upstream's
other seven P4 devices — never received the fix either; only the exact
device the bug was originally reported against did. A diff against upstream
can pass clean while both sides are equally wrong. This check encodes the
correct config directly instead of trusting any single upstream device to
have it.

Usage:
    python3 community/scripts/check_esp32_hosted_psram.py
    python3 community/scripts/check_esp32_hosted_psram.py --self-test
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

MEMPOOL_N_RE = re.compile(r'CONFIG_ESP_HOSTED_USE_MEMPOOL:\s*"n"')
HOSTED_BLOCK_RE = re.compile(r'^esp32_hosted:\s*$', re.MULTILINE)
USE_PSRAM_RE = re.compile(r'^\s*use_psram:\s*true\s*$', re.MULTILINE)


def device_yaml_text(slug, repo_root):
    path = os.path.join(repo_root, "devices", slug, "device", "device.yaml")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def esp32_hosted_block(text):
    """Indented body of the top-level esp32_hosted: block, or "" if absent."""
    lines = text.splitlines()
    out = []
    in_block = False
    for line in lines:
        if HOSTED_BLOCK_RE.match(line):
            in_block = True
            continue
        if in_block:
            if line and not line[0].isspace():
                break
            out.append(line)
    return "\n".join(out)


def check_device_text(slug, text):
    """Return a list of error strings for one device's device.yaml text."""
    block = esp32_hosted_block(text)
    if not block and not HOSTED_BLOCK_RE.search(text):
        return []  # not a hosted-WiFi (P4) device — nothing to check

    if USE_PSRAM_RE.search(block):
        return []

    if MEMPOOL_N_RE.search(text):
        return [
            f'{slug}: esp32_hosted has CONFIG_ESP_HOSTED_USE_MEMPOOL: "n" '
            f"without use_psram: true — this is the exact combination "
            f"behind jtenniswood/espcontrol#1099 (WiFi/API disconnects that "
            f"never recover). Set esp32_hosted: use_psram: true."
        ]
    return [
        f"{slug}: esp32_hosted is configured without use_psram: true — the "
        f"transport buffer pool stays in internal RAM under memory pressure "
        f"this device doesn't have to spare. Set esp32_hosted: "
        f"use_psram: true."
    ]


def check_device(slug, repo_root=None):
    root = repo_root or REPO_ROOT
    text = device_yaml_text(slug, root)
    if text is None:
        return []
    return check_device_text(slug, text)


def check_all(repo_root=None):
    root = repo_root or REPO_ROOT
    with open(os.path.join(root, "community", "devices.json"),
              "r", encoding="utf-8") as f:
        slugs = json.load(f).get("devices", [])
    if not slugs:
        print("No community devices registered. Nothing to check.")
        return 0

    errors = []
    checked = 0
    for slug in slugs:
        text = device_yaml_text(slug, root)
        if text is not None and HOSTED_BLOCK_RE.search(text):
            checked += 1
        errors.extend(check_device(slug, root))

    if errors:
        print("[check_esp32_hosted_psram] FAIL:")
        for msg in errors:
            print(f"  - {msg}")
        return 1
    print(f"[check_esp32_hosted_psram] OK — {checked} hosted-WiFi (ESP32-P4) "
          f"device(s) keep the transport buffer pool in PSRAM")
    return 0


# =============================================================================
# Self-test
# =============================================================================


def self_test():
    print("Running check_esp32_hosted_psram self-test...")
    failures = []

    good = (
        "esp32_hosted:\n"
        "  variant: esp32c6\n"
        "  use_psram: true\n"
        "  reset_pin: GPIO13\n"
        "\n"
        "sdkconfig_options:\n"
        '  CONFIG_ESP_HOSTED_DFLT_TASK_FROM_SPIRAM: "y"\n'
    )
    if check_device_text("good", good):
        failures.append("device with use_psram: true flagged as error")
    else:
        print("  ✓ esp32_hosted with use_psram: true passes")

    bad_mempool = (
        "esp32_hosted:\n"
        "  variant: esp32c6\n"
        "  reset_pin: GPIO13\n"
        "\n"
        "sdkconfig_options:\n"
        '  CONFIG_ESP_HOSTED_USE_MEMPOOL: "n"\n'
    )
    errs = check_device_text("bad-mempool", bad_mempool)
    if not errs or "#1099" not in errs[0]:
        failures.append(f"CONFIG_ESP_HOSTED_USE_MEMPOOL: 'n' without "
                         f"use_psram not caught with the #1099 reference: "
                         f"{errs}")
    else:
        print("  ✓ MEMPOOL: \"n\" without use_psram is caught and cites #1099")

    bad_missing = (
        "esp32_hosted:\n"
        "  variant: esp32c6\n"
        "  reset_pin: GPIO13\n"
    )
    if not check_device_text("bad-missing", bad_missing):
        failures.append("esp32_hosted without use_psram (no mempool line) "
                         "not caught")
    else:
        print("  ✓ esp32_hosted without use_psram is caught even without "
              "the mempool line")

    not_hosted = (
        "psram:\n"
        "  mode: hex\n"
        "  speed: 200MHz\n"
    )
    if check_device_text("s3-device", not_hosted):
        failures.append("device without esp32_hosted at all was flagged")
    else:
        print("  ✓ a device with no esp32_hosted block (e.g. S3) is skipped")

    if failures:
        for msg in failures:
            print(f"[check_esp32_hosted_psram] ERROR: self-test: {msg}",
                  file=sys.stderr)
        return 1
    print("\nAll check_esp32_hosted_psram self-tests passed! ✓")
    return 0


def main():
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    sys.exit(check_all())


if __name__ == "__main__":
    main()
