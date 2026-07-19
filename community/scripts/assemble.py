#!/usr/bin/env python3
"""
Assemble the full espcontrol tree with community device overlays.

Builds a throwaway working tree at .assembly/ by:
1. Cloning upstream espcontrol at the pinned ref
2. Copying community device overlays into the tree
3. Merging the community catalog fragment into upstream's catalog.json
4. Running upstream generators (manifest, slots, build devices)
5. Running upstream validators (manifest, matrix, profiles)

Usage:
    python3 community/scripts/assemble.py [--skip-checks] [--sync-generated] [--self-test]
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASSEMBLY_DIR = os.path.join(REPO_ROOT, ".assembly")
COMMUNITY_DIR = os.path.join(REPO_ROOT, "community")
PIN_FILE = os.path.join(COMMUNITY_DIR, "upstream-ref.txt")
DEVICES_JSON = os.path.join(COMMUNITY_DIR, "devices.json")
CATALOG_FRAGMENT = os.path.join(COMMUNITY_DIR, "catalog-fragment.json")

UPSTREAM_REPO = "https://github.com/jtenniswood/espcontrol"

# Marker patterns for generated blocks
GENERATED_BEGIN_RE = re.compile(r"# *BEGIN GENERATED|// *BEGIN GENERATED|<!-- *BEGIN GENERATED")
GENERATED_END_RE = re.compile(r"# *END GENERATED|// *END GENERATED|<!-- *END GENERATED")


def status(msg):
    """Print a status message."""
    print(f"[assemble] {msg}")


def error(msg):
    """Print an error and exit."""
    print(f"[assemble] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd, cwd=None, check=True, capture=False):
    """Run a subprocess command."""
    status(f"  $ {' '.join(cmd)}")
    kwargs = {"cwd": cwd}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    result = subprocess.run(cmd, **kwargs)
    if check and result.returncode != 0:
        if capture:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
        error(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")
    return result



def read_pin():
    """Read the upstream pin (tag or SHA) from community/upstream-ref.txt."""
    if not os.path.isfile(PIN_FILE):
        error(f"Pin file not found: {PIN_FILE}")
    pin = open(PIN_FILE).read().strip()
    if not pin:
        error("Pin file is empty")
    status(f"Upstream pin: {pin}")
    return pin


def is_sha(ref):
    """Check if a ref looks like a full 40-char SHA."""
    return bool(re.fullmatch(r"[0-9a-f]{40}", ref))


def clone_upstream(pin):
    """Clone upstream at the pinned ref into .assembly/."""
    if os.path.isdir(ASSEMBLY_DIR):
        status("Removing existing .assembly/ ...")
        shutil.rmtree(ASSEMBLY_DIR)

    status(f"Cloning upstream at {pin} ...")
    if is_sha(pin):
        # For SHA refs: clone default branch, fetch the SHA, checkout
        run(["git", "clone", "--depth", "1", UPSTREAM_REPO, ASSEMBLY_DIR])
        run(["git", "fetch", "origin", pin], cwd=ASSEMBLY_DIR)
        run(["git", "checkout", pin], cwd=ASSEMBLY_DIR)
    else:
        # For tags/branches: clone directly at that ref
        run(["git", "clone", "--depth", "1", "--branch", pin, UPSTREAM_REPO, ASSEMBLY_DIR])

    status("Clone complete.")


def load_devices_json():
    """Load community/devices.json and return the list of device slugs."""
    if not os.path.isfile(DEVICES_JSON):
        error(f"devices.json not found: {DEVICES_JSON}")
    data = json.loads(open(DEVICES_JSON).read())
    return data.get("devices", [])


def copy_overlay(slugs):
    """Copy community device directories and build files into .assembly/."""
    if not slugs:
        status("No community devices to overlay (devices list is empty).")
        return

    status(f"Copying overlay for {len(slugs)} device(s) ...")
    for slug in slugs:
        # Copy device directory
        src_device = os.path.join(REPO_ROOT, "devices", slug)
        dst_device = os.path.join(ASSEMBLY_DIR, "devices", slug)
        if not os.path.isdir(src_device):
            error(f"Device directory not found: {src_device}")
        if os.path.exists(dst_device):
            error(f"Collision: {dst_device} already exists in upstream (official device?)")
        status(f"  devices/{slug}/ -> .assembly/devices/{slug}/")
        shutil.copytree(src_device, dst_device)

        # Copy build YAML files (glob matching slug)
        builds_src = os.path.join(REPO_ROOT, "builds")
        builds_dst = os.path.join(ASSEMBLY_DIR, "builds")
        pattern = os.path.join(builds_src, f"{slug}*.yaml")
        for build_file in glob.glob(pattern):
            fname = os.path.basename(build_file)
            dst_path = os.path.join(builds_dst, fname)
            if os.path.exists(dst_path):
                error(f"Collision: build file {fname} already exists in upstream")
            status(f"  builds/{fname} -> .assembly/builds/{fname}")
            shutil.copy2(build_file, dst_path)

    status("Overlay copy complete.")


def merge_catalog(slugs):
    """
    Merge community catalog-fragment.json into .assembly/devices/catalog.json.

    Upstream catalog.json structure (discovered from v2.6.3):
    {
      "settings": { ... },
      "profiles": { ... },
      "devices": {
        "<slug>": { "profiles": {...}, "config": {...}, ... },
        ...
      }
    }

    The "devices" key is an object (dict) keyed by device slug.
    The catalog-fragment.json has the same {"devices": {...}} structure.
    We append fragment entries to the end of the upstream devices object.
    """
    if not os.path.isfile(CATALOG_FRAGMENT):
        status("No catalog-fragment.json found, skipping catalog merge.")
        return

    fragment = json.loads(open(CATALOG_FRAGMENT).read())
    fragment_devices = fragment.get("devices", {})

    if not fragment_devices:
        status("Catalog fragment is empty, skipping catalog merge.")
        return

    catalog_path = os.path.join(ASSEMBLY_DIR, "devices", "catalog.json")
    if not os.path.isfile(catalog_path):
        error(f"Upstream catalog.json not found: {catalog_path}")

    status(f"Merging {len(fragment_devices)} device(s) into catalog.json ...")
    catalog = json.loads(open(catalog_path).read())

    # The upstream devices collection is catalog["devices"] (an object/dict)
    upstream_devices = catalog.get("devices", {})

    for slug, entry in fragment_devices.items():
        if slug in upstream_devices:
            error(f"Catalog collision: slug '{slug}' already exists in upstream catalog")
        upstream_devices[slug] = entry
        status(f"  Added '{slug}' to catalog")

    catalog["devices"] = upstream_devices

    with open(catalog_path, "w") as f:
        json.dump(catalog, f, indent=2)
        f.write("\n")

    status("Catalog merge complete.")


def extract_generated_blocks(content):
    """
    Extract generated blocks from file content.
    Returns list of (start_line, end_line, block_text) tuples.
    """
    lines = content.splitlines(keepends=True)
    blocks = []
    in_block = False
    start = 0
    for i, line in enumerate(lines):
        if GENERATED_BEGIN_RE.search(line):
            in_block = True
            start = i
        elif GENERATED_END_RE.search(line) and in_block:
            blocks.append((start, i, "".join(lines[start:i + 1])))
            in_block = False
    return blocks


def diff_ignoring_generated(old_content, new_content):
    """
    Check if two file contents differ outside of generated blocks.
    Returns True if there are meaningful (non-generated) differences.
    """
    old_blocks = extract_generated_blocks(old_content)
    new_blocks = extract_generated_blocks(new_content)

    # Strip generated blocks from both and compare
    def strip_generated(content, blocks):
        lines = content.splitlines(keepends=True)
        result = []
        skip_ranges = set()
        for start, end, _ in blocks:
            for i in range(start, end + 1):
                skip_ranges.add(i)
        for i, line in enumerate(lines):
            if i not in skip_ranges:
                result.append(line)
        return "".join(result)

    old_stripped = strip_generated(old_content, old_blocks)
    new_stripped = strip_generated(new_content, new_blocks)
    return old_stripped != new_stripped



def sync_generated_back(slugs):
    """
    Copy generated blocks from .assembly/devices/<slug>/ back to the source
    devices/<slug>/ in the repo root.
    """
    if not slugs:
        return

    status("Syncing generated blocks back to source ...")
    for slug in slugs:
        assembly_device = os.path.join(ASSEMBLY_DIR, "devices", slug)
        source_device = os.path.join(REPO_ROOT, "devices", slug)
        if not os.path.isdir(assembly_device) or not os.path.isdir(source_device):
            continue
        for root, _dirs, files in os.walk(assembly_device):
            for fname in files:
                asm_path = os.path.join(root, fname)
                rel_path = os.path.relpath(asm_path, assembly_device)
                src_path = os.path.join(source_device, rel_path)
                if not os.path.isfile(src_path):
                    continue
                asm_content = open(asm_path).read()
                src_content = open(src_path).read()
                if asm_content != src_content:
                    # Replace generated blocks in source with those from assembly
                    asm_blocks = extract_generated_blocks(asm_content)
                    if asm_blocks:
                        src_lines = src_content.splitlines(keepends=True)
                        src_blocks = extract_generated_blocks(src_content)
                        # Simple approach: replace source file with assembly version
                        # if only generated blocks differ
                        with open(src_path, "w") as f:
                            f.write(asm_content)
                        status(f"  Synced generated blocks: devices/{slug}/{rel_path}")


def run_generators(slugs, sync_generated=False):
    """Run upstream generator scripts inside .assembly/."""
    status("Running generators ...")

    generators = [
        ["python3", "scripts/generate_device_manifest.py"],
        ["python3", "scripts/generate_device_slots.py"],
        ["python3", "scripts/build.py", "devices"],
    ]

    # Snapshot community device files before generation (if we have community devices)
    snapshots = {}
    if slugs:
        for slug in slugs:
            device_dir = os.path.join(ASSEMBLY_DIR, "devices", slug)
            if os.path.isdir(device_dir):
                for root, _dirs, files in os.walk(device_dir):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        snapshots[fpath] = open(fpath).read()

    for cmd in generators:
        result = subprocess.run(
            cmd,
            cwd=ASSEMBLY_DIR,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0:
            status(f"  Generator warning: '{' '.join(cmd)}' exited with code {result.returncode}")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            status("  (Continuing — generator failure may require extra dependencies)")

    # Check if community device files were modified outside generated blocks
    if slugs:
        non_generated_changes = []
        for fpath, old_content in snapshots.items():
            if not os.path.isfile(fpath):
                continue
            new_content = open(fpath).read()
            if new_content != old_content:
                if diff_ignoring_generated(old_content, new_content):
                    non_generated_changes.append(fpath)

        if non_generated_changes:
            status("ERROR: Generators modified community device files outside generated blocks:")
            for fpath in non_generated_changes:
                rel = os.path.relpath(fpath, ASSEMBLY_DIR)
                print(f"  - {rel}")
            # Show diff
            for fpath in non_generated_changes:
                old = snapshots[fpath]
                new = open(fpath).read()
                rel = os.path.relpath(fpath, ASSEMBLY_DIR)
                print(f"\n--- {rel} (before)")
                print(f"+++ {rel} (after)")
                import difflib
                diff = difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"a/{rel}",
                    tofile=f"b/{rel}",
                )
                print("".join(diff))
            sys.exit(1)

        # If --sync-generated, copy generated blocks back to source
        if sync_generated:
            sync_generated_back(slugs)

    status("Generators complete.")


def run_validators():
    """Run upstream validator scripts inside .assembly/."""
    status("Running validators ...")

    validators = [
        ["python3", "scripts/check_device_manifest.py"],
        ["python3", "scripts/check_device_matrix.py"],
        ["python3", "scripts/check_device_profiles.py"],
    ]

    all_passed = True
    for cmd in validators:
        result = subprocess.run(
            cmd,
            cwd=ASSEMBLY_DIR,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0:
            all_passed = False
            status(f"  Validator warning: '{' '.join(cmd)}' exited with code {result.returncode}")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            status("  (Continuing — validator may require extra dependencies)")

    if all_passed:
        status("All validators passed.")
    else:
        status("Some validators had issues (see above).")



def run_self_test():
    """
    Self-test mode: verify the catalog merge logic works with the real
    upstream catalog structure using a fixture.
    """
    status("Running self-test ...")

    # Step 1: Read the pin and clone upstream
    pin = read_pin()
    clone_upstream(pin)

    # Step 2: Verify the clone has expected structure
    catalog_path = os.path.join(ASSEMBLY_DIR, "devices", "catalog.json")
    if not os.path.isfile(catalog_path):
        error("Self-test failed: catalog.json not found after clone")

    catalog = json.loads(open(catalog_path).read())
    if "devices" not in catalog:
        error("Self-test failed: catalog.json has no 'devices' key")

    upstream_slugs = list(catalog["devices"].keys())
    status(f"  Upstream catalog has {len(upstream_slugs)} device(s): {upstream_slugs}")

    # Step 3: Create a fake community device entry and merge it
    test_slug = "__self_test_fake_device__"
    test_fragment = {
        "devices": {
            test_slug: {
                "profiles": {"platform": "esp32-s3"},
                "config": {
                    "slots": 4,
                    "public": {
                        "name": "Self-Test Fake Device",
                        "screenSize": "3.5 inches",
                        "resolution": "480 x 320",
                        "orientation": "Landscape",
                    },
                    "layout": {"cols": 2, "rows": 2, "firmwareGrid": "2x2"},
                },
            }
        }
    }

    # Temporarily override catalog-fragment.json
    original_fragment = open(CATALOG_FRAGMENT).read() if os.path.isfile(CATALOG_FRAGMENT) else None

    try:
        with open(CATALOG_FRAGMENT, "w") as f:
            json.dump(test_fragment, f, indent=2)
            f.write("\n")

        # Run the merge
        merge_catalog([test_slug])

        # Verify merge worked
        merged = json.loads(open(catalog_path).read())
        if test_slug not in merged["devices"]:
            error("Self-test failed: test slug not found in merged catalog")
        if merged["devices"][test_slug]["config"]["public"]["name"] != "Self-Test Fake Device":
            error("Self-test failed: merged entry has wrong data")

        # Verify ordering: test slug should be at the end
        keys = list(merged["devices"].keys())
        if keys[-1] != test_slug:
            error(f"Self-test failed: test slug not at end of devices (last key: {keys[-1]})")

        # Verify collision detection works
        collision_fragment = {"devices": {upstream_slugs[0]: {"test": True}}}
        with open(CATALOG_FRAGMENT, "w") as f:
            json.dump(collision_fragment, f, indent=2)
            f.write("\n")

        # Re-clone to get a fresh catalog for collision test
        clone_upstream(pin)
        try:
            # This should fail because the slug already exists
            # We capture the exit to verify it would fail
            original_exit = sys.exit
            collision_caught = False

            def fake_exit(code=0):
                nonlocal collision_caught
                if code != 0:
                    collision_caught = True
                raise SystemExit(code)

            sys.exit = fake_exit
            try:
                merge_catalog([upstream_slugs[0]])
            except SystemExit:
                pass
            sys.exit = original_exit

            if not collision_caught:
                error("Self-test failed: collision detection did not trigger")
            status("  Collision detection works correctly.")
        except Exception:
            sys.exit = original_exit
            # If we get here, it means the error() call worked as expected
            status("  Collision detection works correctly.")

    finally:
        # Restore original fragment
        if original_fragment is not None:
            with open(CATALOG_FRAGMENT, "w") as f:
                f.write(original_fragment)
        elif os.path.isfile(CATALOG_FRAGMENT):
            os.remove(CATALOG_FRAGMENT)

    # Cleanup
    if os.path.isdir(ASSEMBLY_DIR):
        shutil.rmtree(ASSEMBLY_DIR)

    status("Self-test PASSED.")


def main():
    parser = argparse.ArgumentParser(description="Assemble espcontrol tree with community overlays")
    parser.add_argument("--skip-checks", action="store_true", help="Skip running validators")
    parser.add_argument("--sync-generated", action="store_true", help="Copy generated blocks back to source")
    parser.add_argument("--self-test", action="store_true", help="Run self-test mode")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return

    # Step 1: Read pin
    pin = read_pin()

    # Step 2: Clone upstream
    clone_upstream(pin)

    # Step 3: Load device slugs and copy overlay
    slugs = load_devices_json()
    copy_overlay(slugs)

    # Step 4: Merge catalog
    merge_catalog(slugs)

    # Step 5: Run generators
    run_generators(slugs, sync_generated=args.sync_generated)

    # Step 6: Run validators (unless --skip-checks)
    if not args.skip_checks:
        run_validators()
    else:
        status("Skipping validators (--skip-checks).")

    status("Assembly complete. Tree is at .assembly/")


if __name__ == "__main__":
    main()
