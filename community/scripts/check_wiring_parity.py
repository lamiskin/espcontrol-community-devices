#!/usr/bin/env python3
"""
check_wiring_parity.py – Catch community devices drifting from upstream's
generated wiring between ref bumps.

Usage:
    UPSTREAM_CLONE=.assembly python3 community/scripts/check_wiring_parity.py
    python3 community/scripts/check_wiring_parity.py --self-test

Why this exists
---------------
A ref bump regenerates the content *inside* each device's
`// BEGIN/END GENERATED` markers, and assemble.py's outside-generated-blocks
check catches the generator rewriting anything else. Between those two, the
call sites that upstream's generator emits *around* those markers are only
compared if the generator actually changes them — so when upstream switches a
device to a different helper based on a catalog flag we never set, both checks
stay green and the device quietly keeps the old wiring.

That happened: upstream v2.9.0 emits `grid_rebuild_all(...)` in
`apply_button_grid` for every device that sets
`firmware.display.refreshRebuildsSubpages`, and a rotation-capable device that
does not set it keeps `grid_refresh_layout(...)` — which relayouts existing
widgets instead of recreating them, so rotating the panel can leave secondary
cards bound to a previous definition. All eight community devices enable
rotation; none set the flag. Nothing failed. The bump reported success.

check_include_parity.py compares `common/` include *paths* against an upstream
reference device. This does the same for wiring: it compares which helper each
script calls, so a future upstream switch fails the ref bump instead of
shipping.

Checks per device:
  1. Rotation-capable devices must rebuild subpages on refresh — i.e. carry
     firmware.display.refreshRebuildsSubpages, and therefore emit
     grid_rebuild_all in apply_button_grid rather than grid_refresh_layout.
     This mirrors upstream's own test_rotation_refresh_rebuilds_subpages.
  2. No device still calls a helper that its same-chip upstream reference
     device has stopped calling.
"""

import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
COMMUNITY_DIR = os.path.join(REPO_ROOT, "community")
DEVICES_JSON = os.path.join(COMMUNITY_DIR, "devices.json")
CATALOG_FRAGMENT = os.path.join(COMMUNITY_DIR, "catalog-fragment.json")
DEVICES_DIR = os.path.join(REPO_ROOT, "devices")

UPSTREAM_CLONE = os.environ.get(
    "UPSTREAM_CLONE", os.path.join(REPO_ROOT, ".assembly"))

# Same split as check_include_parity.py: one upstream device per chip family.
REFERENCE_DEVICES = {
    "esp32-s3": "guition-esp32-s3-4848s040",
    "esp32-p4": "guition-esp32-p4-jc1060p470",
}

# Helpers whose presence/absence is meaningful to compare. Keep this list
# small and deliberate — it is a drift tripwire, not a diff.
TRACKED_HELPERS = (
    "grid_rebuild_all",
    "grid_refresh_layout",
)


def load_devices():
    with open(DEVICES_JSON, encoding="utf-8") as f:
        return json.load(f)["devices"]


def load_catalog():
    with open(CATALOG_FRAGMENT, encoding="utf-8") as f:
        return json.load(f)["devices"]


def device_platform(entry):
    return ((entry.get("profiles") or {}).get("platform") or "").lower()


def rotation_enabled(entry):
    cfg = entry.get("config") or {}
    return bool((cfg.get("rotation") or {}).get("enabled"))


def refresh_rebuilds_subpages(entry):
    cfg = entry.get("config") or {}
    display = (cfg.get("firmware") or {}).get("display") or {}
    return bool(display.get("refreshRebuildsSubpages"))


def apply_button_grid_block(sensors_text):
    """The apply_button_grid script body, where the refresh helper is called.

    Falls back to refresh_button_grid for the pre-v2.9.0 layout, where the
    lambda lived directly in that script instead of a separate one.
    """
    for start in ("  - id: apply_button_grid", "  - id: refresh_button_grid"):
        if start in sensors_text:
            rest = sensors_text.split(start, 1)[1]
            return rest.split("  - id: refresh_subpage_grid", 1)[0]
    return None


def helpers_called(block):
    return {h for h in TRACKED_HELPERS if re.search(rf"\b{h}\s*\(", block)}


def check_device(slug, entry, sensors_text, reference_text):
    """Return a list of problem strings for one device."""
    problems = []

    block = apply_button_grid_block(sensors_text)
    if block is None:
        return [f"{slug}: no apply_button_grid/refresh_button_grid script found"]

    called = helpers_called(block)

    # 1. Rotation implies rebuild-on-refresh.
    if rotation_enabled(entry):
        if not refresh_rebuilds_subpages(entry):
            problems.append(
                f"{slug}: rotation is enabled but "
                f"firmware.display.refreshRebuildsSubpages is not set — "
                f"rotating can leave secondary cards bound to a stale "
                f"definition (set it in community/catalog-fragment.json)"
            )
        if "grid_rebuild_all" not in called:
            problems.append(
                f"{slug}: rotation is enabled but apply_button_grid does not "
                f"call grid_rebuild_all — re-run assemble.py after setting "
                f"refreshRebuildsSubpages and sync device/sensors.yaml"
            )

    # 2. Don't keep calling a helper the upstream reference has dropped.
    if reference_text is not None:
        ref_block = apply_button_grid_block(reference_text)
        if ref_block is not None:
            ref_called = helpers_called(ref_block)
            for helper in sorted(called - ref_called):
                problems.append(
                    f"{slug}: apply_button_grid calls {helper}(), which the "
                    f"upstream reference device no longer calls — upstream "
                    f"wiring changed and this device was not regenerated"
                )

    return problems


def read_reference(platform):
    slug = REFERENCE_DEVICES.get(platform)
    if not slug:
        return None, None
    path = os.path.join(UPSTREAM_CLONE, "devices", slug, "device", "sensors.yaml")
    if not os.path.isfile(path):
        return slug, None
    with open(path, encoding="utf-8") as f:
        return slug, f.read()


def check_wiring_parity():
    if not os.path.isdir(UPSTREAM_CLONE):
        print(f"Upstream clone not found at {UPSTREAM_CLONE} — "
              f"run community/scripts/assemble.py first", file=sys.stderr)
        return 1

    devices = load_devices()
    catalog = load_catalog()
    all_problems = []

    for slug in devices:
        entry = catalog.get(slug)
        if entry is None:
            all_problems.append(
                f"{slug}: listed in devices.json but missing from "
                f"catalog-fragment.json")
            continue

        sensors_path = os.path.join(DEVICES_DIR, slug, "device", "sensors.yaml")
        if not os.path.isfile(sensors_path):
            all_problems.append(f"{slug}: device/sensors.yaml not found")
            continue
        with open(sensors_path, encoding="utf-8") as f:
            sensors_text = f.read()

        platform = device_platform(entry)
        ref_slug, ref_text = read_reference(platform)
        if ref_slug is None:
            all_problems.append(
                f"{slug}: no upstream reference device for platform "
                f"'{platform or '(unset)'}'")
            continue

        problems = check_device(slug, entry, sensors_text, ref_text)
        if problems:
            all_problems.extend(problems)
        else:
            print(f"Wiring parity OK: {slug} (ref: {ref_slug})")

    if all_problems:
        print(f"\nWiring parity drift found ({len(all_problems)}):",
              file=sys.stderr)
        for p in all_problems:
            print(f"  ✗ {p}", file=sys.stderr)
        return 1

    print(f"\nWiring parity check passed ({len(devices)} device(s)).")
    return 0


# =============================================================================
# Self-test
# =============================================================================


REF_OK = """\
script:
  - id: refresh_button_grid
    then:
      - script.execute: apply_button_grid
  - id: apply_button_grid
    then:
      - lambda: |-
          grid_rebuild_all(slots, cfg, sp_cfgs,
            id(main_page)->obj);
  - id: refresh_subpage_grid
    then:
      - lambda: |-
          grid_rebuild_all(slots, cfg, sp_cfgs,
            id(main_page)->obj);
"""

DEV_STALE = """\
script:
  - id: refresh_button_grid
    then:
      - script.execute: apply_button_grid
  - id: apply_button_grid
    then:
      - lambda: |-
          grid_refresh_layout(slots, cfg,
            id(main_page)->obj);
  - id: refresh_subpage_grid
    then:
      - lambda: |-
          grid_rebuild_all(slots, cfg, sp_cfgs,
            id(main_page)->obj);
"""


def self_test():
    print("Running check_wiring_parity self-test...")

    rotating_unset = {
        "profiles": {"platform": "esp32-s3"},
        "config": {"rotation": {"enabled": True}},
    }
    rotating_set = {
        "profiles": {"platform": "esp32-s3"},
        "config": {
            "rotation": {"enabled": True},
            "firmware": {"display": {"refreshRebuildsSubpages": True}},
        },
    }
    static_dev = {
        "profiles": {"platform": "esp32-s3"},
        "config": {"rotation": {"enabled": False}},
    }

    # 1. The real regression: rotating device, flag unset, stale helper.
    problems = check_device("dev-a", rotating_unset, DEV_STALE, REF_OK)
    assert problems, "expected drift to be reported"
    assert any("refreshRebuildsSubpages" in p for p in problems), problems
    assert any("grid_rebuild_all" in p for p in problems), problems
    assert any("grid_refresh_layout" in p for p in problems), problems
    print("  ✓ Stale rotating device is flagged")

    # 2. Correctly wired device passes.
    problems = check_device("dev-b", rotating_set, REF_OK, REF_OK)
    assert problems == [], problems
    print("  ✓ Correctly wired device passes")

    # 3. Flag set but sensors.yaml not regenerated yet.
    problems = check_device("dev-c", rotating_set, DEV_STALE, REF_OK)
    assert any("does not call grid_rebuild_all" in p for p in problems), problems
    assert not any("refreshRebuildsSubpages is not set" in p
                   for p in problems), problems
    print("  ✓ Flag-set-but-not-regenerated is flagged")

    # 4. Non-rotating device is not forced to rebuild, but still must not
    #    call a helper upstream dropped.
    problems = check_device("dev-d", static_dev, DEV_STALE, REF_OK)
    assert not any("rotation is enabled" in p for p in problems), problems
    assert any("grid_refresh_layout" in p for p in problems), problems
    print("  ✓ Non-rotating device only flagged for dropped helper")

    # 5. Missing script is reported rather than silently passing.
    problems = check_device("dev-e", rotating_set, "script:\n", REF_OK)
    assert any("no apply_button_grid" in p for p in problems), problems
    print("  ✓ Missing refresh script is reported")

    # 6. Pre-v2.9.0 layout (lambda inline in refresh_button_grid) is parsed.
    legacy = DEV_STALE.replace("  - id: apply_button_grid\n", "")
    block = apply_button_grid_block(legacy)
    assert block is not None and "grid_refresh_layout" in block
    print("  ✓ Legacy single-script layout is still parsed")

    print("\nAll check_wiring_parity self-tests passed! ✓")


def main():
    parser = argparse.ArgumentParser(
        description="Check community devices against upstream wiring")
    parser.add_argument("--self-test", action="store_true",
                        help="Run self-test mode")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    sys.exit(check_wiring_parity())


if __name__ == "__main__":
    main()
