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
  2. Set parity with the same-chip upstream reference device: the scripts
     defined and the helpers called must match in both directions. This is
     deliberately generic — it compares sets rather than a list of known
     names, so a helper introduced upstream after this check was written
     still trips it. That is the point: the drift it was written for was
     found by a contributor, not by us.

Known-legitimate divergence goes in ACCEPTED_DIVERGENCE with a reason,
rather than being absorbed silently by a broad allowlist.
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

# Deliberately NOT a list of known helpers. An allowlist only ever catches
# the drift we already know about — the whole reason this check exists is
# that grid_rebuild_all was found by a contributor, not by us. Instead we
# compare the *sets* of scripts defined and helpers called against the
# upstream reference device, so a helper nobody here has heard of yet still
# trips it.
#
# Words that appear as `name(` in these files but are not upstream helpers.
CALL_NOISE = frozenset({
    "id", "if", "for", "while", "return", "switch", "sizeof", "lambda",
    "else", "catch", "defined", "static_cast", "reinterpret_cast",
})

# Divergences from the reference device that are known-legitimate. Empty by
# design: add an entry only with a reason, so a real finding is never
# silently absorbed. Format: slug -> {"scripts": {...}, "calls": {...}}
ACCEPTED_DIVERGENCE = {}


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


def helpers_called(text):
    """Every `name(` in the text that looks like an upstream helper call."""
    found = set(re.findall(r"\b([a-z_][a-z0-9_]{3,})\s*\(", text))
    return found - CALL_NOISE


def scripts_defined(text):
    """The set of `- id: <name>` script definitions."""
    return set(re.findall(r"^  - id: (\S+)", text, re.M))


def check_device(slug, entry, sensors_text, reference_text):
    """Return a list of problem strings for one device."""
    problems = []

    block = apply_button_grid_block(sensors_text)
    if block is None:
        return [f"{slug}: no apply_button_grid/refresh_button_grid script found"]

    called = helpers_called(block)   # apply_button_grid scope only

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

    # 2. Set parity against the upstream reference device, in both
    #    directions. No list of known helpers — anything upstream calls that
    #    we never call (or vice versa) is drift, including helpers that did
    #    not exist when this check was written.
    if reference_text is not None:
        accepted = ACCEPTED_DIVERGENCE.get(slug, {})
        ok_scripts = set(accepted.get("scripts", ()))
        ok_calls = set(accepted.get("calls", ()))

        ref_scripts, our_scripts = scripts_defined(reference_text), scripts_defined(sensors_text)
        ref_calls, our_calls = helpers_called(reference_text), helpers_called(sensors_text)

        for name in sorted(ref_scripts - our_scripts - ok_scripts):
            problems.append(
                f"{slug}: upstream's reference device defines script "
                f"'{name}' and this device does not — upstream restructured "
                f"and this device was not regenerated")
        for name in sorted(our_scripts - ref_scripts - ok_scripts):
            problems.append(
                f"{slug}: defines script '{name}' that upstream's reference "
                f"device does not — upstream dropped it, or it is a local "
                f"addition that needs an ACCEPTED_DIVERGENCE entry")
        for name in sorted(ref_calls - our_calls - ok_calls):
            problems.append(
                f"{slug}: upstream's reference device calls {name}() and "
                f"this device never does — upstream wiring changed")
        for name in sorted(our_calls - ref_calls - ok_calls):
            problems.append(
                f"{slug}: calls {name}(), which upstream's reference device "
                f"no longer does — this device was not regenerated")

    return problems


# device.yaml keys that legitimately differ per device — pin assignments,
# peripherals, per-board tuning. Comparing device.yaml structure finds real
# drift (panel_config was missing on 7 of 8 devices) but also a lot of this,
# which is why that comparison advises rather than fails.
DEVICE_YAML_EXPECTED_DIFFS = frozenset({
    "scl", "sda", "switch", "button", "sensor", "binary_sensor", "number",
    "build_flags", "max_connections", "cpu_frequency", "setup_priority",
    "api", "i2c", "uart", "spi", "light", "output", "mdi_font_file",
})


def device_yaml_drift(slug, platform):
    """Structural differences in device.yaml vs the reference. Advisory."""
    ref = REFERENCE_DEVICES.get(platform)
    ref_path = os.path.join(UPSTREAM_CLONE, "devices", ref or "",
                            "device", "device.yaml")
    our_path = os.path.join(DEVICES_DIR, slug, "device", "device.yaml")
    if not ref or not os.path.isfile(ref_path) or not os.path.isfile(our_path):
        return []
    ref_text, our_text = open(ref_path).read(), open(our_path).read()

    def keys(text):
        return (set(re.findall(r"^([a-z_]+):", text, re.M))
                | set(re.findall(r"^  ([a-z_]+):", text, re.M)))

    missing = keys(ref_text) - keys(our_text) - DEVICE_YAML_EXPECTED_DIFFS
    return sorted(missing)


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
    advisories = []

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

        # Advisory only — device.yaml carries genuinely per-device content
        # (pins, peripherals, board tuning), so this reports for review at
        # ref-bump time rather than failing the build.
        for key in device_yaml_drift(slug, platform):
            advisories.append(
                f"{slug}: device.yaml has no '{key}:' block, but upstream's "
                f"reference device ({ref_slug}) does")

    if all_problems:
        print(f"\nWiring parity drift found ({len(all_problems)}):",
              file=sys.stderr)
        for p in all_problems:
            print(f"  ✗ {p}", file=sys.stderr)
        return 1

    if advisories:
        print(f"\nAdvisory — device.yaml structure differs from upstream "
              f"({len(advisories)}). Not a failure; review at ref-bump time:")
        for a in advisories:
            print(f"  · {a}")

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

    # 7. The property that actually matters: a helper nobody has heard of.
    #    An allowlist-based check can only ever catch known drift, and the
    #    drift this script exists for was found by a contributor rather than
    #    by us. So: invent a helper, put it only upstream, and require that
    #    it trips — without the script knowing anything about it.
    ref_novel = REF_OK.replace(
        "          grid_rebuild_all(slots, cfg, sp_cfgs,",
        "          grid_frobnicate_v3(slots);\n          grid_rebuild_all(slots, cfg, sp_cfgs,")
    problems = check_device("dev-f", rotating_set, REF_OK, ref_novel)
    assert any("grid_frobnicate_v3" in p for p in problems), problems
    print("  ✓ Novel upstream helper is caught without being listed anywhere")

    # 8. And in the other direction: a script upstream adds that we lack.
    ref_new_script = REF_OK.replace(
        "  - id: refresh_subpage_grid",
        "  - id: rebind_sensor_subscriptions\n    then:\n      - lambda: |-\n"
        "          ha_reannounce_state_subscriptions();\n  - id: refresh_subpage_grid")
    problems = check_device("dev-g", rotating_set, REF_OK, ref_new_script)
    assert any("rebind_sensor_subscriptions" in p for p in problems), problems
    print("  ✓ Script added upstream is caught")

    # 9. ACCEPTED_DIVERGENCE suppresses a known-legitimate difference, so a
    #    real local addition does not force weakening the whole check.
    ours_extra = REF_OK.replace(
        "  - id: refresh_subpage_grid",
        "  - id: community_only_helper\n    then:\n      - lambda: |-\n"
        "          do_community_thing();\n  - id: refresh_subpage_grid")
    problems = check_device("dev-h", rotating_set, ours_extra, REF_OK)
    assert any("community_only_helper" in p for p in problems), problems
    ACCEPTED_DIVERGENCE["dev-h"] = {
        "scripts": {"community_only_helper"}, "calls": {"do_community_thing"}}
    try:
        problems = check_device("dev-h", rotating_set, ours_extra, REF_OK)
        assert problems == [], problems
    finally:
        ACCEPTED_DIVERGENCE.pop("dev-h", None)
    print("  ✓ ACCEPTED_DIVERGENCE suppresses a recorded difference")

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
