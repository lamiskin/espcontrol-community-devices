#!/usr/bin/env python3
"""
check_include_parity.py – Verify that community device packages.yaml files
include the same set of common/ paths as the upstream reference device for
their chip family.

Usage:
    python3 community/scripts/check_include_parity.py
    python3 community/scripts/check_include_parity.py --self-test
"""

import argparse
import json
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
COMMUNITY_DIR = os.path.join(REPO_ROOT, "community")
DEVICES_JSON = os.path.join(COMMUNITY_DIR, "devices.json")
CATALOG_FRAGMENT = os.path.join(COMMUNITY_DIR, "catalog-fragment.json")
PIN_FILE = os.path.join(COMMUNITY_DIR, "upstream-ref.txt")

# Upstream reference clone (read-only)
UPSTREAM_CLONE = os.environ.get(
    "UPSTREAM_CLONE",
    "/Users/lachlan/Kiro/espcontrol"
)

# Reference devices per chip family
REFERENCE_DEVICES = {
    "esp32-s3": "guition-esp32-s3-4848s040",
    "esp32-p4": "guition-esp32-p4-jc1060p470",
}


def read_pin():
    """Read the upstream pin from community/upstream-ref.txt."""
    with open(PIN_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def get_chip_family(slug):
    """Get the chip family for a device slug from catalog-fragment."""
    with open(CATALOG_FRAGMENT, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    device_entry = catalog.get("devices", {}).get(slug, {})
    platform = device_entry.get("profiles", {}).get("platform", "")
    return platform


def extract_common_paths_from_remote(content):
    """
    Extract common/ paths from a remote-package-form packages.yaml.

    Looks for lines like:
      - common/config/entity_names.yaml
      - path: common/config/button_template_4chunk.yaml
    inside files: blocks of upstream_X entries.
    """
    paths = set()
    in_files_block = False

    for line in content.splitlines():
        stripped = line.strip()

        if stripped == "files:":
            in_files_block = True
            continue

        if in_files_block:
            # Mapping item first: - path: common/path/to/file.yaml
            match = re.match(r'^-\s+path:\s*(\S+)', stripped)
            if match:
                path = match.group(1)
                if path.startswith("common/"):
                    paths.add(path)
                continue

            # Simple list item: - common/path/to/file.yaml
            match = re.match(r'^-\s+(\S+)', stripped)
            if match:
                path = match.group(1)
                if path.startswith("common/"):
                    paths.add(path)
                continue

            # Continuation keys (path: without dash, vars:)
            if stripped.startswith("path:"):
                match = re.match(r'^path:\s*(\S+)', stripped)
                if match:
                    path = match.group(1)
                    if path.startswith("common/"):
                        paths.add(path)
                continue

            # vars: line (continuation of previous path entry)
            if stripped.startswith("vars:"):
                continue

            # If we hit a non-list line that's not indented enough,
            # we've left the files: block
            if stripped and not stripped.startswith("-"):
                in_files_block = False

    return paths


def extract_common_paths_from_local(content):
    """
    Extract common/ paths from an upstream-style packages.yaml
    (with relative !include ../../common/... paths).
    """
    paths = set()
    for line in content.splitlines():
        # Simple include: key: !include ../../common/path.yaml
        match = re.match(
            r'^\s+\S+:\s+!include\s+\.\./\.\./(.+?)\s*$', line
        )
        if match:
            path = match.group(1)
            if path.startswith("common/"):
                paths.add(path)
            continue

        # Vars include: key: !include { file: ../../common/path, ... }
        match = re.match(
            r'^\s+\S+:\s+!include\s*\{\s*file:\s*\.\./\.\./(.+?),',
            line,
        )
        if match:
            path = match.group(1).strip()
            if path.startswith("common/"):
                paths.add(path)

    return paths


def get_reference_common_paths(chip_family, pin):
    """
    Get common/ paths from the reference device at the pinned version.
    Uses git show on the upstream clone.
    """
    ref_slug = REFERENCE_DEVICES.get(chip_family)
    if not ref_slug:
        return None, f"No reference device for family '{chip_family}'"

    packages_path = f"devices/{ref_slug}/packages.yaml"
    result = subprocess.run(
        ["git", "-C", UPSTREAM_CLONE, "show",
         f"{pin}:{packages_path}"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return None, (
            f"Could not read {packages_path} at {pin}: "
            f"{result.stderr.strip()}"
        )

    content = result.stdout
    paths = extract_common_paths_from_local(content)
    return paths, None


def read_parity_exceptions(slug):
    """
    Read devices/<slug>/parity-exceptions.txt.
    Returns a set of excepted paths.
    """
    exceptions_path = os.path.join(
        REPO_ROOT, "devices", slug, "parity-exceptions.txt"
    )
    if not os.path.isfile(exceptions_path):
        return set()

    exceptions = set()
    with open(exceptions_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip trailing comment
            path = line.split("#")[0].strip()
            if path:
                exceptions.add(path)
    return exceptions


def get_device_common_paths(slug):
    """
    Get common/ paths from a community device's packages.yaml.
    """
    packages_path = os.path.join(
        REPO_ROOT, "devices", slug, "packages.yaml"
    )
    if not os.path.isfile(packages_path):
        return None, f"packages.yaml not found for '{slug}'"

    with open(packages_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check if it's remote form or local form
    if "url:" in content and "files:" in content:
        paths = extract_common_paths_from_remote(content)
    else:
        paths = extract_common_paths_from_local(content)

    return paths, None


def check_parity():
    """Run the include parity check for all community devices."""
    # Load device list
    with open(DEVICES_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    slugs = data.get("devices", [])

    if not slugs:
        print("No community devices registered. Nothing to check.")
        return 0

    pin = read_pin()
    has_errors = False

    for slug in slugs:
        print(f"Checking parity for '{slug}'...")

        # Get chip family
        chip_family = get_chip_family(slug)
        if not chip_family:
            print(f"  WARNING: Could not determine chip family for "
                  f"'{slug}', skipping")
            continue

        # Get reference paths
        ref_paths, err = get_reference_common_paths(chip_family, pin)
        if err:
            print(f"  ERROR: {err}", file=sys.stderr)
            has_errors = True
            continue

        # Get device paths
        device_paths, err = get_device_common_paths(slug)
        if err:
            print(f"  ERROR: {err}", file=sys.stderr)
            has_errors = True
            continue

        # Load exceptions
        exceptions = read_parity_exceptions(slug)

        # Compare
        missing = ref_paths - device_paths - exceptions
        extra = device_paths - ref_paths - exceptions

        if missing:
            has_errors = True
            print(f"  Missing common includes (in reference "
                  f"but not in {slug}):")
            for p in sorted(missing):
                print(f"    - {p}")

        if extra:
            has_errors = True
            print(f"  Extra common includes (in {slug} but not "
                  f"in reference):")
            for p in sorted(extra):
                print(f"    - {p}")

        if not missing and not extra:
            print(f"  ✓ Parity OK (ref: {REFERENCE_DEVICES[chip_family]})")

    return 1 if has_errors else 0


# =============================================================================
# Self-test
# =============================================================================


def self_test():
    """Run embedded self-tests."""
    print("Running check_include_parity self-test...")

    # Test 1: Extract common paths from remote form
    remote_fixture = """\
packages:
  upstream_a:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.6.3
    refresh: 1d
    files:
      - common/config/entity_names.yaml
      - common/assets/icons.yaml
      - common/theme/button.yaml
  device: !include device/device.yaml
  upstream_b:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.6.3
    refresh: 1d
    files:
      - common/config/colors.yaml
      - path: common/config/button_template_4chunk.yaml
        vars: { num: "1" }
      - common/addon/connectivity.yaml
"""
    paths = extract_common_paths_from_remote(remote_fixture)
    expected = {
        "common/config/entity_names.yaml",
        "common/assets/icons.yaml",
        "common/theme/button.yaml",
        "common/config/colors.yaml",
        "common/config/button_template_4chunk.yaml",
        "common/addon/connectivity.yaml",
    }
    assert paths == expected, (
        f"Remote extraction failed.\n"
        f"  Expected: {sorted(expected)}\n"
        f"  Got: {sorted(paths)}"
    )
    print("  ✓ Remote-form path extraction correct")

    # Test 2: Extract common paths from local form
    local_fixture = """\
packages:
  entity_names:    !include ../../common/config/entity_names.yaml
  device:          !include device/device.yaml
  icons:           !include ../../common/assets/icons.yaml
  btn_1:           !include { file: ../../common/config/button_template_4chunk.yaml, vars: { num: "1" } }
  connectivity:    !include ../../common/addon/connectivity.yaml
  lvgl:            !include device/lvgl.yaml
"""
    paths = extract_common_paths_from_local(local_fixture)
    expected = {
        "common/config/entity_names.yaml",
        "common/assets/icons.yaml",
        "common/config/button_template_4chunk.yaml",
        "common/addon/connectivity.yaml",
    }
    assert paths == expected, (
        f"Local extraction failed.\n"
        f"  Expected: {sorted(expected)}\n"
        f"  Got: {sorted(paths)}"
    )
    print("  ✓ Local-form path extraction correct")

    # Test 3: Parity comparison with missing/extra detection
    ref_paths = {
        "common/config/entity_names.yaml",
        "common/assets/icons.yaml",
        "common/addon/connectivity.yaml",
        "common/addon/time.yaml",
    }
    device_paths = {
        "common/config/entity_names.yaml",
        "common/assets/icons.yaml",
        "common/addon/connectivity.yaml",
        "common/addon/backlight.yaml",  # extra
    }
    exceptions = set()

    missing = ref_paths - device_paths - exceptions
    extra = device_paths - ref_paths - exceptions

    assert missing == {"common/addon/time.yaml"}, (
        f"Expected time.yaml missing, got: {missing}"
    )
    assert extra == {"common/addon/backlight.yaml"}, (
        f"Expected backlight.yaml extra, got: {extra}"
    )
    print("  ✓ Missing/extra detection correct")

    # Test 4: Parity exceptions filter results
    exceptions = {"common/addon/time.yaml", "common/addon/backlight.yaml"}
    missing = ref_paths - device_paths - exceptions
    extra = device_paths - ref_paths - exceptions
    assert missing == set(), (
        f"Expected no missing after exceptions, got: {missing}"
    )
    assert extra == set(), (
        f"Expected no extra after exceptions, got: {extra}"
    )
    print("  ✓ Parity exceptions correctly filter results")

    print("\nAll check_include_parity self-tests passed! ✓")


def main():
    parser = argparse.ArgumentParser(
        description="Check community device include parity with "
                    "upstream reference"
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run self-test mode"
    )
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    sys.exit(check_parity())


if __name__ == "__main__":
    main()
