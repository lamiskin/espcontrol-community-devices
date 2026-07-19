#!/usr/bin/env python3
"""
check_policy.py – Verify that a PR's changed files comply with the
community devices policy defined in community/DEVICES_POLICY.md.

Usage:
    python3 community/scripts/check_policy.py --base <sha> --head <sha>
    python3 community/scripts/check_policy.py --self-test
"""

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import re

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
POLICY_FILE = os.path.join(
    REPO_ROOT, "community", "DEVICES_POLICY.md"
)
DEVICES_JSON = os.path.join(REPO_ROOT, "community", "devices.json")
CATALOG_FRAGMENT = os.path.join(
    REPO_ROOT, "community", "catalog-fragment.json"
)


def parse_policy(policy_path=None):
    """
    Parse the YAML policy block from DEVICES_POLICY.md.

    Returns a dict of slug -> {allowed: [...], required: [...], forbidden: [...]}
    The special key '_global' contains global rules.
    """
    if policy_path is None:
        policy_path = POLICY_FILE

    with open(policy_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract YAML between markers
    begin_marker = "# --- begin policy ---"
    end_marker = "# --- end policy ---"

    begin_idx = content.find(begin_marker)
    end_idx = content.find(end_marker)

    if begin_idx == -1 or end_idx == -1:
        print("ERROR: Policy markers not found in "
              f"{policy_path}", file=sys.stderr)
        sys.exit(1)

    yaml_text = content[begin_idx + len(begin_marker):end_idx]

    # Simple YAML parser for our known structure
    policy = {}
    current_slug = None
    current_key = None  # 'allowed', 'required', 'forbidden'

    for line in yaml_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Top-level key (slug or _global)
        if not line.startswith(" ") and not line.startswith("\t"):
            # e.g. "_global:" or "my-device:"
            match = re.match(r'^(\S+):\s*$', line)
            if match:
                current_slug = match.group(1)
                policy[current_slug] = {
                    "allowed": [],
                    "required": [],
                    "forbidden": [],
                }
                current_key = None
            continue

        # Second-level key
        if current_slug and re.match(r'^\s{2}\S', line):
            match = re.match(r'^\s+(allowed|required|forbidden):\s*$',
                             line)
            if match:
                current_key = match.group(1)
            continue

        # List item
        if current_slug and current_key:
            match = re.match(r'^\s+-\s+(.+)$', line)
            if match:
                value = match.group(1).strip()
                policy[current_slug][current_key].append(value)

    return policy


def get_changed_files(base, head):
    """Get list of changed files between base and head commits."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Try two-dot diff as fallback
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base}..{head}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        print(f"ERROR: git diff failed: {result.stderr}",
              file=sys.stderr)
        sys.exit(1)
    paths = [p for p in result.stdout.strip().split("\n") if p]
    return paths


def get_touched_slugs(paths):
    """
    Extract device slugs from changed paths.
    A slug is touched if a path matches devices/<slug>/... or
    builds/<slug>[.factory].yaml — builds-only changes (e.g. a hostname
    fix) must still resolve to their owning slug or every such path is
    rejected as unowned.
    """
    slugs = set()
    for path in paths:
        match = re.match(r'^devices/([^/]+)/', path)
        if match:
            slugs.add(match.group(1))
            continue
        match = re.match(r'^builds/(.+?)(\.factory)?\.yaml$', path)
        if match:
            slugs.add(match.group(1))
    return slugs


def path_matches_glob(path, pattern):
    """Check if a path matches a glob pattern using fnmatch."""
    # fnmatch doesn't handle ** well, so we need special handling
    if "**" in pattern:
        # Convert ** to match any number of path segments
        regex_pattern = pattern.replace("**", "DOUBLESTAR")
        regex_pattern = fnmatch.translate(regex_pattern)
        regex_pattern = regex_pattern.replace("DOUBLESTAR", ".*")
        return bool(re.match(regex_pattern, path))
    return fnmatch.fnmatch(path, pattern)


def _slug_dir_exists(slug, existing_files=None):
    """Does devices/<slug>/ still exist (in HEAD)?"""
    if existing_files is not None:
        prefix = f"devices/{slug}/"
        return any(p.startswith(prefix) for p in existing_files)
    return os.path.isdir(os.path.join(REPO_ROOT, "devices", slug))


def _check_paths(paths, policy, devices_json_slugs=None,
                 existing_files=None):
    """
    Core policy check logic. Returns a list of violation messages.

    Args:
        paths: list of changed file paths
        policy: parsed policy dict
        devices_json_slugs: list of slugs from devices.json (for
                           catalog-fragment validation)
        existing_files: if provided, a set of paths considered to exist
                       (for testing without filesystem). If None, uses
                       os.path.isfile against REPO_ROOT.
    """
    if devices_json_slugs is None:
        devices_json_slugs = []

    violations = []
    touched_slugs = get_touched_slugs(paths)

    # A slug whose devices/<slug>/ dir no longer exists is being REMOVED.
    # Its policy block is (correctly) deleted in the same PR, so it gets
    # implicit allowance for exactly its own paths, is exempt from the
    # policy-block and required-files checks, and must be deregistered.
    removed_slugs = {
        slug for slug in touched_slugs
        if not _slug_dir_exists(slug, existing_files)
    }
    for slug in sorted(removed_slugs):
        if slug in devices_json_slugs:
            violations.append(
                f"Device '{slug}' is removed from devices/ but still "
                f"registered in devices.json"
            )

    # Check 1: Each path must match at least one allowed glob
    global_allowed = policy.get("_global", {}).get("allowed", [])

    for path in paths:
        allowed = False

        # Check global allowed patterns
        for pattern in global_allowed:
            if path_matches_glob(path, pattern):
                allowed = True
                break

        # Check slug-specific allowed patterns
        if not allowed:
            for slug in touched_slugs:
                slug_policy = policy.get(slug, {})
                patterns = list(slug_policy.get("allowed", []))
                if slug in removed_slugs:
                    patterns += [f"devices/{slug}/**",
                                 f"builds/{slug}*.yaml"]
                for pattern in patterns:
                    if path_matches_glob(path, pattern):
                        allowed = True
                        break
                if allowed:
                    break

        if not allowed:
            violations.append(
                f"Path not allowed by policy: {path}"
            )

    # Check 2: If catalog-fragment.json changed, every modified/added
    # entry's slug must be in devices.json
    if "community/catalog-fragment.json" in paths:
        catalog_path = CATALOG_FRAGMENT
        if os.path.isfile(catalog_path):
            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)
            for slug in catalog.get("devices", {}):
                if slug not in devices_json_slugs:
                    violations.append(
                        f"Catalog fragment has slug '{slug}' not in "
                        f"devices.json"
                    )

    # Check 3: If a PR touches a device slug directory, that slug
    # must have a policy block (removed slugs delete theirs)
    for slug in touched_slugs:
        if slug not in policy and slug not in removed_slugs:
            violations.append(
                f"Device slug '{slug}' is touched but has no "
                f"policy block in DEVICES_POLICY.md"
            )

    # Check 4: Check required files exist for touched slugs
    # (skip removed slugs — their files are gone by design)
    for slug in touched_slugs - removed_slugs:
        slug_policy = policy.get(slug, {})
        for required_path in slug_policy.get("required", []):
            if existing_files is not None:
                exists = required_path in existing_files
            else:
                full_path = os.path.join(REPO_ROOT, required_path)
                exists = os.path.isfile(full_path)
            if not exists:
                violations.append(
                    f"Required file missing for '{slug}': "
                    f"{required_path}"
                )

    # Check 5: Check no forbidden paths are touched
    all_forbidden = []
    # Global forbidden
    all_forbidden.extend(
        policy.get("_global", {}).get("forbidden", [])
    )
    # Slug-specific forbidden
    for slug in touched_slugs:
        slug_policy = policy.get(slug, {})
        all_forbidden.extend(slug_policy.get("forbidden", []))

    for path in paths:
        for pattern in all_forbidden:
            if path_matches_glob(path, pattern):
                violations.append(
                    f"Forbidden path touched: {path} "
                    f"(matches pattern '{pattern}')"
                )
                break

    return violations


def run_check(base, head):
    """Run the full policy check."""
    policy = parse_policy()
    paths = get_changed_files(base, head)

    if not paths:
        print("No changed files found.")
        return 0

    # Load devices.json
    devices_json_slugs = []
    if os.path.isfile(DEVICES_JSON):
        with open(DEVICES_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        devices_json_slugs = data.get("devices", [])

    violations = _check_paths(paths, policy, devices_json_slugs)

    if violations:
        print("Policy violations found:", file=sys.stderr)
        for v in violations:
            print(f"  ✗ {v}", file=sys.stderr)
        return 1

    print(f"Policy check passed ({len(paths)} file(s) checked).")
    return 0


# =============================================================================
# Self-test
# =============================================================================


def self_test():
    """Run embedded self-tests."""
    print("Running check_policy self-test...")

    # A policy with _global and a device slug
    policy = {
        "_global": {
            "allowed": [
                "community/**",
                "README.md",
                ".github/**",
                "LICENSE",
                "NOTICE",
            ],
            "required": [],
            "forbidden": [
                "common/**",
                "components/**",
            ],
        },
        "my-device": {
            "allowed": [
                "devices/my-device/**",
                "builds/my-device*.yaml",
            ],
            "required": [
                "devices/my-device/device/device.yaml",
            ],
            "forbidden": [],
        },
    }

    # Simulate existing files for required-file checks
    existing_files = {
        "devices/my-device/device/device.yaml",
    }

    # Test 1: Global paths pass
    global_paths = [
        "community/foo.txt",
        "README.md",
        ".github/bar.yml",
    ]
    violations = _check_paths(
        global_paths, policy, existing_files=existing_files
    )
    assert violations == [], (
        f"Expected no violations for global paths, got: {violations}"
    )
    print("  ✓ Global paths pass (community/**, README.md, "
          ".github/**)")

    # Test 2: Device-specific path passes
    device_paths = ["devices/my-device/device/device.yaml"]
    violations = _check_paths(
        device_paths, policy, existing_files=existing_files
    )
    assert violations == [], (
        f"Expected no violations for device path, got: {violations}"
    )
    print("  ✓ Device-specific path passes")

    # Test 3: Disallowed path fails
    bad_paths = ["some/random/file.txt"]
    violations = _check_paths(
        bad_paths, policy, existing_files=existing_files
    )
    assert len(violations) > 0, "Expected violations for bad path"
    assert "not allowed" in violations[0].lower(), (
        f"Expected 'not allowed' violation, got: {violations[0]}"
    )
    print("  ✓ Disallowed path correctly rejected")

    # Test 4: Forbidden path detection
    forbidden_paths = ["common/foo.yaml"]
    violations = _check_paths(
        forbidden_paths, policy, existing_files=existing_files
    )
    assert any("forbidden" in v.lower() for v in violations), (
        f"Expected forbidden violation, got: {violations}"
    )
    print("  ✓ Forbidden path detected (common/foo.yaml)")

    forbidden_paths2 = ["components/x.cpp"]
    violations = _check_paths(
        forbidden_paths2, policy, existing_files=existing_files
    )
    assert any("forbidden" in v.lower() for v in violations), (
        f"Expected forbidden violation, got: {violations}"
    )
    print("  ✓ Forbidden path detected (components/x.cpp)")

    # Test 5: Missing policy block for touched slug (the device dir must
    # exist in HEAD, otherwise it counts as a removal — see Test 7)
    unknown_slug_paths = ["devices/unknown-device/file.yaml"]
    violations = _check_paths(
        unknown_slug_paths, policy,
        existing_files=existing_files | {"devices/unknown-device/file.yaml"},
    )
    assert any("no policy block" in v.lower() for v in violations), (
        f"Expected missing policy block violation, got: {violations}"
    )
    print("  ✓ Missing policy block detected for unknown slug")

    # Test 6: Build file for known slug passes
    build_paths = ["builds/my-device.yaml"]
    violations = _check_paths(
        build_paths + ["devices/my-device/device/device.yaml"],
        policy,
        existing_files=existing_files,
    )
    assert not any("not allowed" in v.lower() for v in violations), (
        f"Build file should be allowed, got: {violations}"
    )
    print("  ✓ Build file for known slug passes")

    # Test 7: Full device removal passes — device dir absent from HEAD,
    # policy block deleted in the same PR, slug deregistered
    removal_paths = [
        "devices/old-device/device/device.yaml",
        "devices/old-device/packages.yaml",
        "builds/old-device.yaml",
        "builds/old-device.factory.yaml",
        "community/devices.json",
        "community/DEVICES_POLICY.md",
        "community/STATUS.md",
    ]
    violations = _check_paths(
        removal_paths, policy,
        devices_json_slugs=["my-device"],
        existing_files=existing_files,
    )
    assert violations == [], (
        f"Expected clean removal to pass, got: {violations}"
    )
    print("  ✓ Full device removal passes")

    # Test 8: Removal while still registered in devices.json fails
    violations = _check_paths(
        removal_paths, policy,
        devices_json_slugs=["my-device", "old-device"],
        existing_files=existing_files,
    )
    assert any("still registered" in v for v in violations), (
        f"Expected still-registered violation, got: {violations}"
    )
    print("  ✓ Removal while still registered is rejected")

    # Test 9: Builds-only change resolves to its owning slug
    builds_only = ["builds/my-device.factory.yaml"]
    violations = _check_paths(
        builds_only, policy, existing_files=existing_files
    )
    assert violations == [], (
        f"Expected builds-only change to pass, got: {violations}"
    )
    print("  ✓ Builds-only change passes via owning slug")

    print("\nAll check_policy self-tests passed! ✓")


def main():
    parser = argparse.ArgumentParser(
        description="Check PR files against community devices policy"
    )
    parser.add_argument("--base", help="Base commit SHA")
    parser.add_argument("--head", help="Head commit SHA")
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run self-test mode"
    )
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    if not args.base or not args.head:
        parser.error("--base and --head are required")

    sys.exit(run_check(args.base, args.head))


if __name__ == "__main__":
    main()
