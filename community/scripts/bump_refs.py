#!/usr/bin/env python3
"""
bump_refs.py – Update all upstream espcontrol ref pins in device YAML files.

Usage:
    python3 community/scripts/bump_refs.py <new-ref>
    python3 community/scripts/bump_refs.py --self-test

The <new-ref> must be either a tag like vX.Y.Z or a 40-character SHA.

Algorithm:
1. Validate the new ref format.
2. For each .yaml file under devices/:
   - Replace ref: lines within blocks that have url:.*jtenniswood/espcontrol
   - Replace espcontrol_component_ref: "..." values
3. Write the new ref to community/upstream-ref.txt.
4. Run check_pin_consistency.py as a post-condition.
5. Print summary.

Idempotent: running with the current pin is a no-op.
"""

import argparse
import glob
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
COMMUNITY_DIR = os.path.join(REPO_ROOT, "community")
PIN_FILE = os.path.join(COMMUNITY_DIR, "upstream-ref.txt")
DEVICES_DIR = os.path.join(REPO_ROOT, "devices")
CHECK_SCRIPT = os.path.join(
    COMMUNITY_DIR, "scripts", "check_pin_consistency.py"
)

# Matches upstream espcontrol URL (jtenniswood org)
UPSTREAM_URL_RE = re.compile(
    r'url:\s*https?://github\.com/jtenniswood/espcontrol'
)

# Matches a ref: line (indented, within a package block)
REF_LINE_RE = re.compile(r'^(\s+ref:\s*)\S+(.*)$')

# Matches espcontrol_component_ref substitution
COMPONENT_REF_RE = re.compile(
    r'^(\s*espcontrol_component_ref:\s*)["\']?(\S+?)["\']?(\s*)$'
)

# Valid ref formats: vX.Y.Z tag or 40-char hex SHA
TAG_RE = re.compile(r'^v\d+\.\d+\.\d+$')
SHA_RE = re.compile(r'^[0-9a-f]{40}$')


def validate_ref(ref):
    """Validate that ref is a tag (vX.Y.Z) or 40-char SHA."""
    if TAG_RE.match(ref):
        return True
    if SHA_RE.match(ref):
        return True
    return False


def read_pin():
    """Read the current pin from community/upstream-ref.txt."""
    if not os.path.isfile(PIN_FILE):
        return None
    with open(PIN_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def write_pin(new_ref):
    """Write the new pin to community/upstream-ref.txt."""
    with open(PIN_FILE, "w", encoding="utf-8") as f:
        f.write(new_ref + "\n")


def bump_yaml_content(content, new_ref):
    """
    Replace upstream espcontrol refs in YAML content.

    Returns (new_content, num_replacements).
    """
    lines = content.splitlines(keepends=True)
    new_lines = []
    replacements = 0
    in_upstream_block = False

    for line in lines:
        stripped = line.strip()

        # Detect upstream URL block entry
        if UPSTREAM_URL_RE.search(line):
            in_upstream_block = True
            new_lines.append(line)
            continue

        # Detect block exit (non-indented line that isn't blank/comment)
        if in_upstream_block and stripped and not line[0].isspace():
            in_upstream_block = False

        # Replace ref: within upstream block
        if in_upstream_block:
            match = REF_LINE_RE.match(line)
            if match:
                old_line = line
                line = match.group(1) + new_ref + match.group(2)
                if not line.endswith('\n') and old_line.endswith('\n'):
                    line += '\n'
                if line != old_line:
                    replacements += 1

        # Replace espcontrol_component_ref anywhere
        match = COMPONENT_REF_RE.match(line)
        if match:
            old_line = line
            # Preserve quoting style
            old_value = match.group(2)
            prefix = match.group(1)
            suffix = match.group(3)
            # Check if original had quotes
            original_line = line
            if '"' in original_line.split('espcontrol_component_ref:')[1]:
                line = prefix + '"' + new_ref + '"' + suffix
            elif "'" in original_line.split('espcontrol_component_ref:')[1]:
                line = prefix + "'" + new_ref + "'" + suffix
            else:
                line = prefix + new_ref + suffix
            if not line.endswith('\n') and old_line.endswith('\n'):
                line += '\n'
            if line != old_line:
                replacements += 1

        new_lines.append(line)

    return "".join(new_lines), replacements


def bump_refs(new_ref):
    """
    Bump all upstream refs in device YAML files to new_ref.

    Returns the number of files modified.
    """
    # Find all YAML files under devices/
    pattern = os.path.join(DEVICES_DIR, "**", "*.yaml")
    yaml_files = glob.glob(pattern, recursive=True)

    files_modified = 0

    for filepath in sorted(yaml_files):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        new_content, replacements = bump_yaml_content(content, new_ref)

        if replacements > 0:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            files_modified += 1

    return files_modified


def run_consistency_check():
    """Run check_pin_consistency.py as a post-condition."""
    result = subprocess.run(
        [sys.executable, CHECK_SCRIPT],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Post-condition FAILED: pin consistency check failed.",
              file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.stdout:
            print(result.stdout)
        return False
    if result.stdout:
        print(result.stdout.strip())
    return True


# =============================================================================
# Self-test
# =============================================================================


def self_test():
    """Run embedded self-tests."""
    print("Running bump_refs self-test...")

    # Test 1: Validate ref formats
    assert validate_ref("v2.6.3") is True
    assert validate_ref("v10.0.1") is True
    assert validate_ref("abc123") is False
    assert validate_ref("main") is False
    assert validate_ref("a" * 40) is True  # valid SHA
    assert validate_ref("g" * 40) is False  # not valid hex
    print("  ✓ Ref validation works")

    # Test 2: Bump ref: in upstream block
    old_yaml = """\
packages:
  upstream_a:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.5.0
    refresh: 1d
    files:
      - common/config/entity_names.yaml
  upstream_b:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.5.0
    refresh: 1d
    files:
      - common/addon/connectivity.yaml
"""
    new_content, count = bump_yaml_content(old_yaml, "v2.6.3")
    assert count == 2, f"Expected 2 replacements, got {count}"
    assert "ref: v2.6.3" in new_content
    assert "ref: v2.5.0" not in new_content
    print("  ✓ ref: lines in upstream blocks updated")

    # Test 3: Bump espcontrol_component_ref (quoted)
    old_yaml2 = """\
substitutions:
  espcontrol_component_ref: "v2.5.0"
  device_slug: "my-device"
"""
    new_content2, count2 = bump_yaml_content(old_yaml2, "v2.6.3")
    assert count2 == 1, f"Expected 1 replacement, got {count2}"
    assert 'espcontrol_component_ref: "v2.6.3"' in new_content2
    print("  ✓ espcontrol_component_ref (quoted) updated")

    # Test 4: Non-upstream ref: lines are NOT touched
    other_yaml = """\
packages:
  some_other:
    url: https://github.com/other/repo
    ref: v1.0.0
    files:
      - some/file.yaml
"""
    new_content3, count3 = bump_yaml_content(other_yaml, "v2.6.3")
    assert count3 == 0, f"Expected 0 replacements, got {count3}"
    assert "ref: v1.0.0" in new_content3
    print("  ✓ Non-upstream ref: lines not touched")

    # Test 5: Idempotence (running with same ref = no-op)
    already_correct = """\
packages:
  upstream_a:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.6.3
    refresh: 1d
    files:
      - common/config/entity_names.yaml

substitutions:
  espcontrol_component_ref: "v2.6.3"
"""
    new_content4, count4 = bump_yaml_content(already_correct, "v2.6.3")
    assert count4 == 0, f"Expected 0 replacements (idempotent), got {count4}"
    assert new_content4 == already_correct
    print("  ✓ Idempotent: same ref produces no changes")

    # Test 6: SHA ref works
    sha = "a" * 40
    old_yaml_sha = """\
packages:
  upstream_a:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.5.0
    refresh: 1d
    files:
      - common/config/entity_names.yaml
"""
    new_content5, count5 = bump_yaml_content(old_yaml_sha, sha)
    assert count5 == 1
    assert f"ref: {sha}" in new_content5
    print("  ✓ SHA ref format works")

    # Test 7: Combined file with both ref types
    combined = """\
packages:
  upstream_a:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.5.0
    refresh: 1d
    files:
      - common/config/entity_names.yaml
  device: !include device/device.yaml
  upstream_b:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.5.0
    refresh: 1d
    files:
      - common/addon/connectivity.yaml

substitutions:
  espcontrol_component_ref: "v2.5.0"
"""
    new_content6, count6 = bump_yaml_content(combined, "v2.7.0")
    assert count6 == 3, f"Expected 3 replacements, got {count6}"
    assert "ref: v2.5.0" not in new_content6
    assert 'espcontrol_component_ref: "v2.5.0"' not in new_content6
    print("  ✓ Combined ref: and espcontrol_component_ref updated")

    print("\nAll bump_refs self-tests passed! ✓")


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Bump upstream espcontrol ref in all device YAML files"
    )
    parser.add_argument(
        "new_ref", nargs="?",
        help="New ref (vX.Y.Z tag or 40-char SHA)"
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run self-test mode"
    )
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    if not args.new_ref:
        parser.error("new_ref is required (or use --self-test)")

    new_ref = args.new_ref

    # Validate ref format
    if not validate_ref(new_ref):
        print(
            f"Error: '{new_ref}' is not a valid ref. "
            f"Must be vX.Y.Z or a 40-character SHA.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check if already at this pin (idempotent)
    current_pin = read_pin()
    if current_pin == new_ref:
        print(f"Pin is already {new_ref}. Nothing to do.")
        sys.exit(0)

    # Bump all refs
    files_modified = bump_refs(new_ref)

    # Update pin file
    write_pin(new_ref)

    # Run consistency check as post-condition
    if not run_consistency_check():
        sys.exit(1)

    print(f"Updated {files_modified} files, pin is now {new_ref}")


if __name__ == "__main__":
    main()
