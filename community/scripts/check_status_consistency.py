#!/usr/bin/env python3
"""
check_status_consistency.py – Enforce the invariants tying STATUS.md,
devices.json, catalog-fragment.json, DEVICES_POLICY.md, and the actual
devices/ + builds/ trees together.

Several of these were violated at some point (a STATUS row surviving its
device's removal; a device merged without ever compiling; a half-done
removal breaking assemble). The pages/installer and nightly tooling all
parse STATUS.md positionally, so drift is otherwise silent.

Invariants:
  1. Every slug in devices.json has: a STATUS row, devices/<slug>/ with the
     required files, builds/<slug>.yaml + builds/<slug>.factory.yaml, a
     catalog-fragment entry, and a DEVICES_POLICY.md block.
  2. Every STATUS row's status is one of Working | Untested | Broken | Parked.
  3. Working/Untested/Broken rows must be registered in devices.json;
     Parked rows must NOT be registered and must NOT have a device dir.
  4. No orphan devices/<slug>/ dirs or builds/<slug>*.yaml outside
     devices.json.
  5. No duplicate slugs in STATUS.md; devices.json is sorted alphabetically.

Usage:
    python3 community/scripts/check_status_consistency.py
    python3 community/scripts/check_status_consistency.py --self-test
"""

import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

VALID_STATUSES = {"Working", "Untested", "Broken", "Parked"}
IN_REPO_STATUSES = {"Working", "Untested", "Broken"}
REQUIRED_DEVICE_FILES = ("esphome.yaml", "packages.yaml",
                         os.path.join("device", "device.yaml"))


def parse_status_rows(status_path):
    """Return list of (name, slug, status) from the STATUS.md table."""
    rows = []
    with open(status_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = [p.strip() for p in line.split("|")]
            # | Name | slug | Status | Last verified | Owner | Source |
            if len(parts) >= 5 and parts[1] and parts[2]:
                if parts[2] in ("Slug", "------", ""):
                    continue
                if set(parts[2]) <= {"-"}:
                    continue
                rows.append((parts[1], parts[2], parts[3]))
    return rows


def parse_policy_slugs(policy_path):
    """Slugs that have a policy block (top-level keys except _global)."""
    with open(policy_path, "r", encoding="utf-8") as f:
        content = f.read()
    begin = content.find("# --- begin policy ---")
    end = content.find("# --- end policy ---")
    if begin == -1 or end == -1:
        return None
    slugs = set()
    for line in content[begin:end].splitlines():
        match = re.match(r'^([A-Za-z0-9_-]+):\s*$', line)
        if match and match.group(1) != "_global":
            slugs.add(match.group(1))
    return slugs


def check(repo_root=None):
    root = repo_root or REPO_ROOT
    problems = []

    def p(msg):
        problems.append(msg)

    with open(os.path.join(root, "community", "devices.json")) as f:
        registered = json.load(f)["devices"]
    with open(os.path.join(root, "community",
                           "catalog-fragment.json")) as f:
        catalog_slugs = set(json.load(f).get("devices", {}))
    rows = parse_status_rows(
        os.path.join(root, "community", "STATUS.md"))
    policy_slugs = parse_policy_slugs(
        os.path.join(root, "community", "DEVICES_POLICY.md"))
    if policy_slugs is None:
        p("DEVICES_POLICY.md: policy markers not found")
        policy_slugs = set()

    status_by_slug = {}
    for name, slug, status in rows:
        if slug in status_by_slug:
            p(f"STATUS.md: duplicate row for slug '{slug}'")
        status_by_slug[slug] = status
        if status not in VALID_STATUSES:
            p(f"STATUS.md: '{slug}' has invalid status '{status}' "
              f"(expected one of {sorted(VALID_STATUSES)})")

    # Registered devices: fully wired
    for slug in registered:
        if slug not in status_by_slug:
            p(f"devices.json: '{slug}' has no STATUS.md row")
        elif status_by_slug[slug] == "Parked":
            p(f"'{slug}' is registered in devices.json but STATUS says "
              f"Parked (Parked means not in the repo)")
        device_dir = os.path.join(root, "devices", slug)
        if not os.path.isdir(device_dir):
            p(f"devices.json: '{slug}' has no devices/{slug}/ directory")
        else:
            for rel in REQUIRED_DEVICE_FILES:
                if not os.path.isfile(os.path.join(device_dir, rel)):
                    p(f"'{slug}': missing devices/{slug}/{rel}")
        for build in (f"builds/{slug}.yaml", f"builds/{slug}.factory.yaml"):
            if not os.path.isfile(os.path.join(root, build)):
                p(f"'{slug}': missing {build}")
        if slug not in catalog_slugs:
            p(f"'{slug}': missing catalog-fragment.json entry")
        if slug not in policy_slugs:
            p(f"'{slug}': missing DEVICES_POLICY.md block")

    # STATUS rows: statuses match registration reality
    for slug, status in status_by_slug.items():
        if status in IN_REPO_STATUSES and slug not in registered:
            p(f"STATUS.md: '{slug}' is {status} but not registered in "
              f"devices.json (use Parked for devices not in the repo)")
        if status == "Parked":
            if os.path.isdir(os.path.join(root, "devices", slug)):
                p(f"STATUS.md: '{slug}' is Parked but devices/{slug}/ "
                  f"exists")

    # Orphans
    devices_dir = os.path.join(root, "devices")
    if os.path.isdir(devices_dir):
        for entry in sorted(os.listdir(devices_dir)):
            if not os.path.isdir(os.path.join(devices_dir, entry)):
                continue
            if entry not in registered:
                p(f"orphan device directory not in devices.json: "
                  f"devices/{entry}/")
    builds_dir = os.path.join(root, "builds")
    if os.path.isdir(builds_dir):
        for entry in sorted(os.listdir(builds_dir)):
            match = re.match(r'^(.+?)(\.factory)?\.yaml$', entry)
            if match and match.group(1) not in registered:
                p(f"orphan build profile not in devices.json: "
                  f"builds/{entry}")

    # Extra registries
    for slug in sorted(catalog_slugs - set(registered)):
        p(f"catalog-fragment.json: '{slug}' is not in devices.json")
    for slug in sorted(policy_slugs - set(registered)):
        p(f"DEVICES_POLICY.md: block for '{slug}' but not in devices.json")

    # Ordering
    if registered != sorted(registered):
        p("devices.json: slugs are not sorted alphabetically")

    return problems


def self_test():
    import shutil
    import tempfile

    failures = []
    tmp = tempfile.mkdtemp(prefix="status_consistency_test_")

    def build_repo(status_rows, registered, catalog, policy_slugs,
                   device_dirs, builds):
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(os.path.join(tmp, "community"))
        with open(os.path.join(tmp, "community", "devices.json"), "w") as f:
            json.dump({"devices": registered}, f)
        with open(os.path.join(tmp, "community",
                               "catalog-fragment.json"), "w") as f:
            json.dump({"devices": {s: {} for s in catalog}}, f)
        lines = ["# Status", "", "| Device | Slug | Status | V | O | S |",
                 "|---|---|---|---|---|---|"]
        for name, slug, status in status_rows:
            lines.append(f"| {name} | {slug} | {status} | - | @x | y |")
        with open(os.path.join(tmp, "community", "STATUS.md"), "w") as f:
            f.write("\n".join(lines) + "\n")
        policy = ["# --- begin policy ---", "_global:", "  allowed:",
                  "    - community/**"]
        for s in policy_slugs:
            policy += [f"{s}:", "  allowed:", f"    - devices/{s}/**"]
        policy.append("# --- end policy ---")
        with open(os.path.join(tmp, "community",
                               "DEVICES_POLICY.md"), "w") as f:
            f.write("\n".join(policy) + "\n")
        os.makedirs(os.path.join(tmp, "builds"), exist_ok=True)
        for b in builds:
            open(os.path.join(tmp, "builds", b), "w").write("x: 1\n")
        for d in device_dirs:
            dd = os.path.join(tmp, "devices", d, "device")
            os.makedirs(dd, exist_ok=True)
            for rel in ("esphome.yaml", "packages.yaml"):
                open(os.path.join(tmp, "devices", d, rel), "w").write("a: 1\n")
            open(os.path.join(dd, "device.yaml"), "w").write("a: 1\n")

    # Clean repo passes
    build_repo(
        status_rows=[("Dev A", "dev-a", "Working"),
                     ("Dev P", "dev-p", "Parked")],
        registered=["dev-a"], catalog=["dev-a"], policy_slugs=["dev-a"],
        device_dirs=["dev-a"],
        builds=["dev-a.yaml", "dev-a.factory.yaml"],
    )
    problems = check(tmp)
    if problems:
        failures.append(f"clean repo reported problems: {problems}")

    # Registered but Parked → problem; missing STATUS row → problem
    build_repo(
        status_rows=[("Dev A", "dev-a", "Parked")],
        registered=["dev-a", "dev-b"], catalog=["dev-a", "dev-b"],
        policy_slugs=["dev-a", "dev-b"],
        device_dirs=["dev-a", "dev-b"],
        builds=["dev-a.yaml", "dev-a.factory.yaml",
                "dev-b.yaml", "dev-b.factory.yaml"],
    )
    problems = check(tmp)
    if not any("Parked" in p and "dev-a" in p for p in problems):
        failures.append(f"registered-but-Parked not caught: {problems}")
    if not any("no STATUS.md row" in p for p in problems):
        failures.append(f"missing STATUS row not caught: {problems}")

    # Orphan dir + orphan build + invalid status + unsorted registry
    build_repo(
        status_rows=[("Dev A", "dev-a", "Working"),
                     ("Dev B", "dev-b", "Wonky")],
        registered=["dev-b", "dev-a"], catalog=["dev-a", "dev-b"],
        policy_slugs=["dev-a", "dev-b"],
        device_dirs=["dev-a", "dev-b", "dev-orphan"],
        builds=["dev-a.yaml", "dev-a.factory.yaml", "dev-b.yaml",
                "dev-b.factory.yaml", "dev-ghost.yaml"],
    )
    problems = check(tmp)
    for needle in ("orphan device directory", "orphan build profile",
                   "invalid status", "not sorted"):
        if not any(needle in p for p in problems):
            failures.append(f"'{needle}' not caught: {problems}")

    # Parked with dir present → problem; Broken-but-unregistered → problem
    build_repo(
        status_rows=[("Dev A", "dev-a", "Working"),
                     ("Dev C", "dev-c", "Parked"),
                     ("Dev D", "dev-d", "Broken")],
        registered=["dev-a"], catalog=["dev-a"], policy_slugs=["dev-a"],
        device_dirs=["dev-a", "dev-c"],
        builds=["dev-a.yaml", "dev-a.factory.yaml"],
    )
    problems = check(tmp)
    if not any("Parked but devices/dev-c/ exists" in p for p in problems):
        failures.append(f"Parked-with-dir not caught: {problems}")
    if not any("dev-d" in p and "not registered" in p for p in problems):
        failures.append(f"Broken-unregistered not caught: {problems}")

    shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        for msg in failures:
            print(f"[check_status_consistency] self-test FAIL: {msg}",
                  file=sys.stderr)
        return 1
    print("[check_status_consistency] self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(self_test())

    problems = check()
    if problems:
        print("Status consistency problems found:", file=sys.stderr)
        for msg in problems:
            print(f"  ✗ {msg}", file=sys.stderr)
        sys.exit(1)
    print("Status consistency check passed.")


if __name__ == "__main__":
    main()
