#!/usr/bin/env python3
"""
check_ota_buffer.py – Enforce that every community device enlarges the
http_request buffers enough to follow GitHub Release-asset OTA redirects.

Community firmware is served from GitHub Release assets (see
generate_manifest.py). Those download URLs 302-redirect to a ~950-char signed
CDN URL. esp_http_client's default 512-byte header buffers overflow reading
that Location header / re-sending the long request line
("HTTP_CLIENT: Out of buffer", esp_http_client_open ESP_FAIL), which aborts
the OTA before a single byte is written — so a device that omits this override
silently loses the ability to update.

Each device's packages.yaml must therefore set, in its community-overrides
block, an `http_request:` with buffer_size_rx and buffer_size_tx of at least
MIN_BUFFER bytes (devices ship 4096; the redirect Location alone is ~960).
That block merges with the base http_request in the vendored
common/device/core_infra.yaml.

Usage:
    python3 community/scripts/check_ota_buffer.py
    python3 community/scripts/check_ota_buffer.py --self-test
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
DEVICES_JSON = os.path.join(REPO_ROOT, "community", "devices.json")

# The signed release-asset CDN Location header is ~960 chars; require a
# comfortable margin over that. Devices ship 4096 (hardware-verified).
MIN_BUFFER = 2048


def http_request_buffers(text):
    """
    Extract (buffer_size_rx, buffer_size_tx) from the top-level `http_request:`
    block of a packages.yaml. Returns ints, or None for any key not set.
    """
    rx = tx = None
    in_block = False
    for line in text.splitlines():
        if re.match(r"^http_request:\s*(#.*)?$", line):
            in_block = True
            continue
        if in_block:
            # A new non-indented, non-comment, non-blank line ends the block.
            if line and not line[0].isspace() and not line.lstrip().startswith("#"):
                break
            m = re.match(r"\s+buffer_size_rx:\s*(\d+)", line)
            if m:
                rx = int(m.group(1))
            m = re.match(r"\s+buffer_size_tx:\s*(\d+)", line)
            if m:
                tx = int(m.group(1))
    return rx, tx


def check_device(slug, repo_root=None):
    """Return a list of error strings for one device (empty = OK)."""
    root = repo_root or REPO_ROOT
    path = os.path.join(root, "devices", slug, "packages.yaml")
    if not os.path.isfile(path):
        return [f"{slug}: devices/{slug}/packages.yaml not found"]
    with open(path, "r", encoding="utf-8") as f:
        rx, tx = http_request_buffers(f.read())

    errors = []
    for name, value in (("buffer_size_rx", rx), ("buffer_size_tx", tx)):
        if value is None:
            errors.append(
                f"{slug}: http_request '{name}' is not set in packages.yaml — "
                f"release-asset OTA needs it >= {MIN_BUFFER} to follow the "
                f"redirect (add it to the community-overrides block)")
        elif value < MIN_BUFFER:
            errors.append(
                f"{slug}: http_request '{name}' is {value}, must be "
                f">= {MIN_BUFFER} (release-asset redirect URL is ~960 chars)")
    return errors


def check_all(repo_root=None):
    root = repo_root or REPO_ROOT
    with open(os.path.join(root, "community", "devices.json"),
              "r", encoding="utf-8") as f:
        slugs = json.load(f).get("devices", [])
    if not slugs:
        print("No community devices registered. Nothing to check.")
        return 0

    errors = []
    for slug in slugs:
        errors.extend(check_device(slug, root))

    if errors:
        print("[check_ota_buffer] FAIL:")
        for msg in errors:
            print(f"  - {msg}")
        return 1
    print(f"[check_ota_buffer] OK — {len(slugs)} device(s) set "
          f"http_request buffers >= {MIN_BUFFER}")
    return 0


def self_test():
    import shutil
    import tempfile

    failures = []
    tmp = tempfile.mkdtemp(prefix="check_ota_buffer_test_")
    try:
        def write_device(slug, packages_body):
            d = os.path.join(tmp, "devices", slug)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "packages.yaml"), "w") as f:
                f.write(packages_body)

        good = (
            "packages:\n  device: !include device/device.yaml\n\n"
            "update:\n  - id: !extend firmware_update\n"
            "    source: https://example/manifest.json\n\n"
            "http_request:\n  buffer_size_rx: 4096\n  buffer_size_tx: 4096\n"
        )
        missing = (
            "packages:\n  device: !include device/device.yaml\n\n"
            "update:\n  - id: !extend firmware_update\n"
            "    source: https://example/manifest.json\n"
        )
        rx_only = (
            "http_request:\n  buffer_size_rx: 4096\n"
        )
        too_small = (
            "http_request:\n  buffer_size_rx: 512\n  buffer_size_tx: 512\n"
        )
        # A default (512) http_request that is NOT the override must not be
        # mistaken for a passing value.
        write_device("ok", good)
        write_device("missing", missing)
        write_device("rx-only", rx_only)
        write_device("too-small", too_small)

        os.makedirs(os.path.join(tmp, "community"), exist_ok=True)
        with open(os.path.join(tmp, "community", "devices.json"), "w") as f:
            json.dump({"devices": ["ok", "missing", "rx-only",
                                   "too-small"]}, f)

        if check_device("ok", tmp):
            failures.append("valid override flagged as error")
        if not check_device("missing", tmp):
            failures.append("missing http_request not caught")
        if not check_device("rx-only", tmp):
            failures.append("missing buffer_size_tx not caught")
        errs = check_device("too-small", tmp)
        if len(errs) != 2:
            failures.append(f"too-small: expected 2 errors, got {errs}")

        # Aggregate run must fail when any device is non-compliant.
        if check_all(tmp) == 0:
            failures.append("check_all passed despite bad devices")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        for msg in failures:
            print(f"[check_ota_buffer] ERROR: self-test: {msg}",
                  file=sys.stderr)
        return 1
    print("[check_ota_buffer] self-test passed")
    return 0


def main():
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    sys.exit(check_all())


if __name__ == "__main__":
    main()
