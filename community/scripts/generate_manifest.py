#!/usr/bin/env python3
"""
generate_manifest.py – Generate the ESP Web Tools / OTA manifest for one
device in a release.

Replaces the inline manifest generation that hardcoded name "Espcontrol"
for every device (indistinguishable in the ESP Web Tools dialog) and
silently defaulted the chip family to ESP32-S3 when detection missed —
a wrong chipFamily makes ESP Web Tools refuse to flash the device.

- name: the device's public name from community/catalog-fragment.json
- chipFamily: from devices/<slug>/device/device.yaml — `variant:` first,
  then the `board:` string; anything ambiguous is a HARD ERROR.

Usage:
    python3 community/scripts/generate_manifest.py <slug> \
        --version <version> --tag <tag> --ota-md5 <md5> --output <path>
    python3 community/scripts/generate_manifest.py --self-test
"""

import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

VARIANT_MAP = {
    "esp32s3": "ESP32-S3",
    "esp32p4": "ESP32-P4",
}

# Firmware binaries are served directly from the GitHub Release assets (not
# re-hosted on Pages) so GitHub's per-asset download_count becomes a real
# per-device, per-version, install-vs-OTA metric.
REPO_URL = "https://github.com/lamiskin/espcontrol-community-devices"


def error(msg):
    print(f"[generate_manifest] ERROR: {msg}", file=sys.stderr)


def device_name(slug, repo_root=None):
    """Public device name from the catalog fragment. Hard error if absent."""
    root = repo_root or REPO_ROOT
    fragment_path = os.path.join(
        root, "community", "catalog-fragment.json")
    with open(fragment_path, "r", encoding="utf-8") as f:
        devices = json.load(f).get("devices", {})
    entry = devices.get(slug)
    if entry is None:
        raise ValueError(
            f"slug '{slug}' has no entry in community/catalog-fragment.json")
    name = (entry.get("config", {}).get("public", {}).get("name")
            or entry.get("public", {}).get("name"))
    if not name:
        raise ValueError(
            f"catalog-fragment entry for '{slug}' has no public name")
    return name


def chip_family(slug, repo_root=None):
    """
    Chip family from the device's esp32: block. `variant:` wins; falls back
    to the `board:` string. Raises on anything ambiguous — a silently wrong
    chipFamily produces a manifest ESP Web Tools refuses to flash.
    """
    root = repo_root or REPO_ROOT
    device_yaml = os.path.join(
        root, "devices", slug, "device", "device.yaml")
    with open(device_yaml, "r", encoding="utf-8") as f:
        content = f.read()

    match = re.search(r'^\s*variant:\s*"?([A-Za-z0-9_-]+)"?\s*$',
                      content, re.MULTILINE)
    if match:
        variant = match.group(1).lower().replace("-", "")
        family = VARIANT_MAP.get(variant)
        if family:
            return family
        raise ValueError(
            f"'{slug}': unrecognized esp32 variant '{match.group(1)}' in "
            f"device.yaml — extend VARIANT_MAP in generate_manifest.py if "
            f"this is a new supported chip")

    match = re.search(r'^\s*board:\s*"?([A-Za-z0-9_-]+)"?\s*$',
                      content, re.MULTILINE)
    if match:
        board = match.group(1).lower()
        if "s3" in board:
            return "ESP32-S3"
        if "p4" in board:
            return "ESP32-P4"
        raise ValueError(
            f"'{slug}': cannot infer chip family from board '{match.group(1)}'"
            f" and no variant: is set — add an explicit variant to "
            f"devices/{slug}/device/device.yaml")

    raise ValueError(
        f"'{slug}': device.yaml has neither variant: nor board: — cannot "
        f"determine chip family")


def build_manifest(slug, version, tag, ota_md5, repo_root=None):
    name = device_name(slug, repo_root)
    family = chip_family(slug, repo_root)
    # Absolute download URLs for this tag's release assets. Must be the stable
    # github.com/.../releases/download/... form — it 302-redirects to a
    # short-lived signed CDN URL that is minted per request, so it cannot be
    # pre-resolved into the manifest. Clients (ESP Web Tools, the device's
    # http_request OTA) follow the redirect live.
    dl = f"{REPO_URL}/releases/download/{tag}"
    return {
        "name": name,
        "version": version,
        "home_assistant_domain": "esphome",
        "builds": [
            {
                "chipFamily": family,
                "parts": [
                    {"path": f"{dl}/{slug}.factory.bin", "offset": 0},
                ],
                "ota": {
                    "path": f"{dl}/{slug}.ota.bin",
                    "md5": ota_md5,
                    "release_url": f"{REPO_URL}/releases/tag/{tag}",
                },
            }
        ],
    }


def self_test():
    import shutil
    import tempfile

    failures = []
    tmp = tempfile.mkdtemp(prefix="generate_manifest_test_")
    try:
        def write_device(slug, device_yaml_body):
            d = os.path.join(tmp, "devices", slug, "device")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "device.yaml"), "w") as f:
                f.write(device_yaml_body)

        os.makedirs(os.path.join(tmp, "community"), exist_ok=True)
        fragment = {"devices": {
            "s3-via-board": {"config": {"public": {"name": "Board S3"}}},
            "p4-via-variant": {"config": {"public": {"name": "Variant P4"}}},
            "no-chip-info": {"config": {"public": {"name": "Mystery"}}},
            "flat-public": {"public": {"name": "Flat Name"}},
        }}
        with open(os.path.join(tmp, "community",
                               "catalog-fragment.json"), "w") as f:
            json.dump(fragment, f)

        write_device("s3-via-board",
                     "esp32:\n  board: esp32-s3-devkitc-1\n")
        write_device("p4-via-variant",
                     "esp32:\n  variant: esp32p4\n")
        write_device("no-chip-info", "esp32:\n  flash_size: 16MB\n")
        write_device("flat-public",
                     "esp32:\n  board: esp32s3box\n")

        m = build_manifest("s3-via-board", "1.0", "t", "md5x", tmp)
        if m["name"] != "Board S3" or m["builds"][0]["chipFamily"] != "ESP32-S3":
            failures.append(f"board-based S3 detection failed: {m}")

        # Binary paths must be absolute release-asset download URLs (not the
        # old relative "<slug>.factory.bin"/"<slug>.ota.bin"), else every real
        # install/OTA keeps hitting Pages and download_count stays meaningless.
        build = m["builds"][0]
        dl = f"{REPO_URL}/releases/download/t"
        if build["parts"][0]["path"] != f"{dl}/s3-via-board.factory.bin":
            failures.append(f"factory path not absolute: {build['parts'][0]['path']}")
        if build["ota"]["path"] != f"{dl}/s3-via-board.ota.bin":
            failures.append(f"ota path not absolute: {build['ota']['path']}")
        if build["ota"]["release_url"] != f"{REPO_URL}/releases/tag/t":
            failures.append(f"release_url wrong: {build['ota']['release_url']}")

        m = build_manifest("p4-via-variant", "1.0", "t", "md5x", tmp)
        if m["builds"][0]["chipFamily"] != "ESP32-P4":
            failures.append("variant-based P4 detection failed")

        m = build_manifest("flat-public", "1.0", "t", "md5x", tmp)
        if m["name"] != "Flat Name":
            failures.append("flat public.name fallback failed")

        try:
            build_manifest("no-chip-info", "1.0", "t", "md5x", tmp)
            failures.append("ambiguous chip did NOT raise")
        except ValueError:
            pass

        try:
            build_manifest("not-in-catalog", "1.0", "t", "md5x", tmp)
            failures.append("missing catalog entry did NOT raise")
        except (ValueError, FileNotFoundError):
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        for msg in failures:
            error(f"self-test: {msg}")
        return 1
    print("[generate_manifest] self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", nargs="?")
    parser.add_argument("--version")
    parser.add_argument("--tag")
    parser.add_argument("--ota-md5")
    parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    missing = [n for n, v in (("slug", args.slug),
                              ("--version", args.version),
                              ("--tag", args.tag),
                              ("--ota-md5", args.ota_md5),
                              ("--output", args.output)) if not v]
    if missing:
        parser.error(f"missing required arguments: {', '.join(missing)}")

    try:
        manifest = build_manifest(
            args.slug, args.version, args.tag, args.ota_md5)
    except (ValueError, FileNotFoundError) as exc:
        error(str(exc))
        sys.exit(1)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print(f"[generate_manifest] wrote {args.output} "
          f"({manifest['name']}, {manifest['builds'][0]['chipFamily']})")


if __name__ == "__main__":
    main()
