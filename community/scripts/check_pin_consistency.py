#!/usr/bin/env python3
"""
check_pin_consistency.py – Verify that all device YAML files reference
the correct upstream pin (tag or SHA) from community/upstream-ref.txt.

Usage:
    python3 community/scripts/check_pin_consistency.py
    python3 community/scripts/check_pin_consistency.py --self-test
"""

import argparse
import glob
import os
import re
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
COMMUNITY_DIR = os.path.join(REPO_ROOT, "community")
PIN_FILE = os.path.join(COMMUNITY_DIR, "upstream-ref.txt")
DEVICES_DIR = os.path.join(REPO_ROOT, "devices")

# Pattern matching upstream espcontrol URL variants
UPSTREAM_URL_RE = re.compile(
    r'url:\s*https?://github\.com/'
    r'(jtenniswood|lamiskin)/espcontrol'
)


def read_pin():
    """Read the expected pin from community/upstream-ref.txt."""
    with open(PIN_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def check_yaml_content(content, expected_pin, filepath="<string>"):
    """
    Check a YAML file's content for pin consistency.

    Looks for:
    1. ref: lines within blocks that have url:.*espcontrol
    2. espcontrol_component_ref: values

    Returns list of (line_number, line_text, issue) tuples.
    """
    mismatches = []
    lines = content.splitlines()
    in_upstream_block = False

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Detect upstream URL block entry
        if UPSTREAM_URL_RE.search(line):
            in_upstream_block = True
            continue

        # Detect block exit (non-indented line that isn't blank/comment)
        if in_upstream_block and stripped and not line[0].isspace():
            in_upstream_block = False

        # Check ref: within upstream block
        if in_upstream_block:
            match = re.match(r'^\s+ref:\s*(\S+)', line)
            if match:
                ref_value = match.group(1)
                if ref_value != expected_pin:
                    mismatches.append((
                        i, line.rstrip(),
                        f"ref: {ref_value} (expected {expected_pin})"
                    ))

        # Check espcontrol_component_ref anywhere
        match = re.match(
            r'^\s*espcontrol_component_ref:\s*["\']?(\S+?)["\']?\s*$',
            line,
        )
        if match:
            ref_value = match.group(1)
            if ref_value != expected_pin:
                mismatches.append((
                    i, line.rstrip(),
                    f"espcontrol_component_ref: {ref_value} "
                    f"(expected {expected_pin})"
                ))

    return mismatches


def check_pin_consistency():
    """Run pin consistency check across all device YAML files."""
    expected_pin = read_pin()
    print(f"Expected pin: {expected_pin}")

    # Find all YAML files under devices/
    pattern = os.path.join(DEVICES_DIR, "**", "*.yaml")
    yaml_files = glob.glob(pattern, recursive=True)

    if not yaml_files:
        print("No device YAML files found. Nothing to check.")
        return 0

    all_mismatches = []

    for filepath in sorted(yaml_files):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        mismatches = check_yaml_content(content, expected_pin, filepath)
        if mismatches:
            rel_path = os.path.relpath(filepath, REPO_ROOT)
            for line_num, line_text, issue in mismatches:
                all_mismatches.append(
                    (rel_path, line_num, line_text, issue)
                )

    if all_mismatches:
        print(f"\nPin mismatches found ({len(all_mismatches)}):",
              file=sys.stderr)
        for rel_path, line_num, line_text, issue in all_mismatches:
            print(f"  ✗ {rel_path}:{line_num}: {issue}",
                  file=sys.stderr)
            print(f"    {line_text}", file=sys.stderr)
        return 1

    print(f"Pin consistency check passed "
          f"({len(yaml_files)} file(s) checked).")
    return 0


# =============================================================================
# Self-test
# =============================================================================


def self_test():
    """Run embedded self-tests."""
    print("Running check_pin_consistency self-test...")

    expected_pin = "v2.6.3"

    # Test 1: Correct refs pass
    correct_yaml = """\
packages:
  upstream_a:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.6.3
    refresh: 1d
    files:
      - common/config/entity_names.yaml

substitutions:
  espcontrol_component_ref: v2.6.3
"""
    mismatches = check_yaml_content(correct_yaml, expected_pin)
    assert mismatches == [], (
        f"Expected no mismatches for correct YAML, got: {mismatches}"
    )
    print("  ✓ Correct refs pass validation")

    # Test 2: Wrong ref: detected
    wrong_ref_yaml = """\
packages:
  upstream_a:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.5.0
    refresh: 1d
    files:
      - common/config/entity_names.yaml
"""
    mismatches = check_yaml_content(wrong_ref_yaml, expected_pin)
    assert len(mismatches) == 1, (
        f"Expected 1 mismatch, got {len(mismatches)}: {mismatches}"
    )
    assert "v2.5.0" in mismatches[0][2], (
        f"Expected v2.5.0 in mismatch line, got: {mismatches[0]}"
    )
    print("  ✓ Wrong ref: detected")

    # Test 3: Wrong espcontrol_component_ref detected
    wrong_component_yaml = """\
substitutions:
  espcontrol_component_ref: v2.4.0
  device_slug: "my-device"
"""
    mismatches = check_yaml_content(wrong_component_yaml, expected_pin)
    assert len(mismatches) == 1, (
        f"Expected 1 mismatch, got {len(mismatches)}: {mismatches}"
    )
    assert "espcontrol_component_ref" in mismatches[0][2], (
        f"Expected component_ref in issue, got: {mismatches[0]}"
    )
    print("  ✓ Wrong espcontrol_component_ref detected")

    # Test 4: Multiple mismatches in one file
    multi_wrong_yaml = """\
packages:
  upstream_a:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.5.0
    refresh: 1d
    files:
      - common/config/colors.yaml
  upstream_b:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.4.0
    refresh: 1d
    files:
      - common/addon/connectivity.yaml

substitutions:
  espcontrol_component_ref: v1.0.0
"""
    mismatches = check_yaml_content(multi_wrong_yaml, expected_pin)
    assert len(mismatches) == 3, (
        f"Expected 3 mismatches, got {len(mismatches)}: {mismatches}"
    )
    print("  ✓ Multiple mismatches detected")

    # Test 5: ref: in non-upstream block is ignored
    other_ref_yaml = """\
packages:
  some_other_package:
    url: https://github.com/other/repo
    ref: v1.0.0
    files:
      - some/file.yaml
"""
    mismatches = check_yaml_content(other_ref_yaml, expected_pin)
    assert mismatches == [], (
        f"Expected no mismatches for non-upstream ref, got: {mismatches}"
    )
    print("  ✓ Non-upstream ref: lines ignored")

    # Test 6: lamiskin org URL also checked
    lamiskin_yaml = """\
packages:
  upstream_a:
    url: https://github.com/lamiskin/espcontrol
    ref: v2.5.0
    refresh: 1d
    files:
      - common/config/colors.yaml
"""
    mismatches = check_yaml_content(lamiskin_yaml, expected_pin)
    assert len(mismatches) == 1, (
        f"Expected 1 mismatch for lamiskin URL, got: {mismatches}"
    )
    print("  ✓ lamiskin/espcontrol URL also checked")

    print("\nAll check_pin_consistency self-tests passed! ✓")


def main():
    parser = argparse.ArgumentParser(
        description="Check upstream pin consistency in device YAML files"
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run self-test mode"
    )
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    sys.exit(check_pin_consistency())


if __name__ == "__main__":
    main()
