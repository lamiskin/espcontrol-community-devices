#!/usr/bin/env python3
"""
check_capability_docs.py – Enforce that a device carrying less capability
than a sibling device on the same chip family says so in
catalog-fragment.json, where generate_docs.py renders it as a warning on
that device's public docs page.

Background: upstream releases sometimes add a feature gated behind a
numeric capacity (e.g. v2.10.0's Camera Cards, gated on `imageSlots` going
from 1 to 2 — see community/docs/upstream-ref-bump.md). A ref bump does not
adopt that automatically, since community packages.yaml files are
hand-maintained. Nothing stops a maintainer from quietly leaving one device
behind without ever telling users the feature is missing on that board. This
check makes that silence a CI failure instead: any device whose
`config.capabilities` numbers are lower than the best a sibling device on
the same `profiles.platform` offers must carry a non-empty
`config.capabilityGaps` explaining why — which generate_docs.py then
surfaces as a "not available" warning on the device's page (see
capability_gaps_block()), so the gap can't exist in the catalog without
also existing in what a user reads before installing.

Usage:
    python3 community/scripts/check_capability_docs.py
    python3 community/scripts/check_capability_docs.py --self-test
"""

import argparse
import json
import os
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
CATALOG_FRAGMENT = os.path.join(
    REPO_ROOT, "community", "catalog-fragment.json"
)


def check(catalog_path=None):
    catalog_path = catalog_path or CATALOG_FRAGMENT
    with open(catalog_path, "r", encoding="utf-8") as f:
        devices = json.load(f).get("devices", {})

    problems = []

    # Best capability numbers seen per platform, across all devices.
    best_by_platform = {}
    for slug, entry in devices.items():
        platform = entry.get("profiles", {}).get("platform", "")
        caps = entry.get("config", {}).get("capabilities", {})
        best = best_by_platform.setdefault(platform, {})
        for key, value in caps.items():
            if not isinstance(value, (int, float)):
                continue
            if key not in best or value > best[key]:
                best[key] = value

    for slug, entry in sorted(devices.items()):
        platform = entry.get("profiles", {}).get("platform", "")
        config = entry.get("config", {})
        caps = config.get("capabilities", {})
        gaps = config.get("capabilityGaps", [])
        best = best_by_platform.get(platform, {})

        behind = [
            key for key, value in caps.items()
            if isinstance(value, (int, float))
            and key in best and value < best[key]
        ]
        if behind and not gaps:
            p = (
                f"'{slug}': capabilities {behind} are below the best "
                f"'{platform}' device ({ {k: best[k] for k in behind} }) "
                f"but config.capabilityGaps is empty — add an entry so "
                f"generate_docs.py can warn users on this device's page"
            )
            problems.append(p)

        for i, gap in enumerate(gaps):
            if not isinstance(gap, dict):
                problems.append(
                    f"'{slug}': capabilityGaps[{i}] is not an object")
                continue
            for field in ("feature", "reason"):
                if not gap.get(field):
                    problems.append(
                        f"'{slug}': capabilityGaps[{i}] missing "
                        f"non-empty '{field}'")

    return problems


def self_test():
    import tempfile

    failures = []

    def run(devices):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False
        ) as f:
            json.dump({"devices": devices}, f)
            path = f.name
        try:
            return check(path)
        finally:
            os.unlink(path)

    # A device behind a sibling with no capabilityGaps is a problem.
    problems = run({
        "a": {"profiles": {"platform": "esp32-s3"},
              "config": {"capabilities": {"imageSlots": 2}}},
        "b": {"profiles": {"platform": "esp32-s3"},
              "config": {"capabilities": {"imageSlots": 1}}},
    })
    if not any("'b'" in p and "imageSlots" in p for p in problems):
        failures.append(f"behind-with-no-gap not caught: {problems}")

    # Same, but with a capabilityGaps entry: no problem.
    problems = run({
        "a": {"profiles": {"platform": "esp32-s3"},
              "config": {"capabilities": {"imageSlots": 2}}},
        "b": {"profiles": {"platform": "esp32-s3"},
              "config": {
                  "capabilities": {"imageSlots": 1},
                  "capabilityGaps": [
                      {"feature": "Camera Cards", "reason": "No PSRAM headroom."}
                  ],
              }},
    })
    if problems:
        failures.append(f"documented gap flagged anyway: {problems}")

    # Different platforms are compared separately — a P4 device with fewer
    # slots than an S3 device is not "behind" anything.
    problems = run({
        "a": {"profiles": {"platform": "esp32-s3"},
              "config": {"capabilities": {"imageSlots": 2}}},
        "c": {"profiles": {"platform": "esp32-p4"},
              "config": {"capabilities": {"imageSlots": 1}}},
    })
    if problems:
        failures.append(f"cross-platform comparison flagged: {problems}")

    # Equal capability: no problem, even with no gaps.
    problems = run({
        "a": {"profiles": {"platform": "esp32-s3"},
              "config": {"capabilities": {"imageSlots": 1}}},
        "b": {"profiles": {"platform": "esp32-s3"},
              "config": {"capabilities": {"imageSlots": 1}}},
    })
    if problems:
        failures.append(f"equal capability flagged: {problems}")

    # A capabilityGaps entry missing 'reason' is a problem, even when it
    # would otherwise cover the gap.
    problems = run({
        "a": {"profiles": {"platform": "esp32-s3"},
              "config": {"capabilities": {"imageSlots": 2}}},
        "b": {"profiles": {"platform": "esp32-s3"},
              "config": {
                  "capabilities": {"imageSlots": 1},
                  "capabilityGaps": [{"feature": "Camera Cards"}],
              }},
    })
    if not any("reason" in p for p in problems):
        failures.append(f"missing 'reason' field not caught: {problems}")

    if failures:
        for msg in failures:
            print(f"[check_capability_docs] self-test FAIL: {msg}",
                  file=sys.stderr)
        return 1
    print("[check_capability_docs] self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(self_test())

    problems = check()
    if problems:
        print("Capability documentation problems found:", file=sys.stderr)
        for msg in problems:
            print(f"  ✗ {msg}", file=sys.stderr)
        sys.exit(1)
    print("Capability documentation check passed.")


if __name__ == "__main__":
    main()
