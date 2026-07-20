#!/usr/bin/env python3
"""
check_generated_blocks.py – Verify each device's hand-maintained generated
button block matches what upstream's generator produces at the pin.

Upstream's generate_device_slots.py writes the BEGIN/END GENERATED BUTTON
PACKAGES block in upstream relative-include format and does not understand
this repo's remote-include format, so the community copies are maintained
by hand. On a ref bump, a changed slot count or template file would
otherwise only surface as confusing compile errors.

The generator cannot be replayed against remote-form files, so the
expectation is derived from durable ground truth instead: the merged
manifest's slot count for the device, and the button template its
chip-family reference device uses at the pin. The community block must
contain exactly (reference_template, 1..slots).

Usage:
    python3 community/scripts/check_generated_blocks.py   # needs .assembly/
    python3 community/scripts/check_generated_blocks.py --self-test
"""

import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
ASSEMBLY = os.environ.get(
    "ASSEMBLY_DIR", os.path.join(REPO_ROOT, ".assembly"))

BEGIN = "# BEGIN GENERATED BUTTON PACKAGES"
END = "# END GENERATED BUTTON PACKAGES"

# Remote form (community): "- path: common/config/button_template.yaml"
#                          "  vars: { num: \"3\" }"
REMOTE_PATH_RE = re.compile(
    r'-\s+path:\s*common/config/(button_template[A-Za-z0-9_]*\.yaml)')
VARS_NUM_RE = re.compile(r'vars:\s*\{\s*num:\s*"(\d+)"')


def extract_block(content, source_desc):
    begin_idx = content.find(BEGIN)
    end_idx = content.find(END)
    if begin_idx == -1 or end_idx == -1:
        return None, f"{source_desc}: generated block markers not found"
    return content[begin_idx:end_idx], None


def parse_remote_block(block):
    """(template, num) pairs from remote-include form."""
    pairs = set()
    pending_template = None
    for line in block.splitlines():
        match = REMOTE_PATH_RE.search(line)
        if match:
            pending_template = match.group(1)
        match = VARS_NUM_RE.search(line)
        if match and pending_template:
            pairs.add((pending_template, int(match.group(1))))
    return pairs


REFERENCE_DEVICES = {
    "esp32-s3": "guition-esp32-s3-4848s040",
    "esp32-p4": "guition-esp32-p4-jc1060p470",
}


def chip_family(slug, repo_root=None):
    root = repo_root or REPO_ROOT
    with open(os.path.join(root, "community",
                           "catalog-fragment.json")) as f:
        catalog = json.load(f)
    return catalog.get("devices", {}).get(slug, {}) \
        .get("profiles", {}).get("platform", "")


def reference_template(family, assembly):
    """Template basename the chip-family reference device uses at the pin."""
    ref_slug = REFERENCE_DEVICES.get(family)
    if not ref_slug:
        return None, f"no reference device for chip family '{family}'"
    ref_path = os.path.join(assembly, "devices", ref_slug, "packages.yaml")
    if not os.path.isfile(ref_path):
        return None, f"reference {ref_slug} missing from assembly tree"
    with open(ref_path, encoding="utf-8") as f:
        content = f.read()
    match = re.search(
        r'common/config/(button_template[A-Za-z0-9_]*\.yaml)', content)
    if not match:
        return None, f"no button template found in reference {ref_slug}"
    return match.group(1), None


def check(repo_root=None, assembly=None):
    root = repo_root or REPO_ROOT
    asm = assembly or ASSEMBLY
    problems = []

    with open(os.path.join(root, "community", "devices.json")) as f:
        slugs = json.load(f)["devices"]

    if not os.path.isdir(asm):
        return [f"assembly tree not found at {asm} — run "
                f"community/scripts/assemble.py first"]

    manifest_path = os.path.join(asm, "devices", "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)["devices"]

    for slug in slugs:
        community_path = os.path.join(
            root, "devices", slug, "packages.yaml")
        with open(community_path, encoding="utf-8") as f:
            community_block, err = extract_block(
                f.read(), f"devices/{slug}/packages.yaml")
        if err:
            problems.append(err)
            continue

        slots = (manifest.get(slug) or {}).get("slots")
        if not slots:
            problems.append(f"{slug}: no slots in assembled manifest")
            continue
        family = chip_family(slug, root)
        template, err = reference_template(family, asm)
        if err:
            problems.append(f"{slug}: {err}")
            continue

        expected = {(template, n) for n in range(1, slots + 1)}
        actual = parse_remote_block(community_block)

        if actual != expected:
            missing = expected - actual
            extra = actual - expected
            detail = []
            if missing:
                detail.append(f"missing {sorted(missing)[:3]}"
                              f"{'…' if len(missing) > 3 else ''}")
            if extra:
                detail.append(f"extra {sorted(extra)[:3]}"
                              f"{'…' if len(extra) > 3 else ''}")
            problems.append(
                f"{slug}: generated button block drifted — expected "
                f"{slots}x {template}; {'; '.join(detail)}")

    return problems


def self_test():
    import shutil
    import tempfile

    failures = []
    tmp = tempfile.mkdtemp(prefix="genblock_test_")

    def community_block(template, count):
        entries = "".join(
            f"      - path: common/config/{template}\n"
            f"        vars: {{ num: \"{n}\" }}\n"
            for n in range(1, count + 1))
        return ("packages:\n  upstream_c:\n    files:\n"
                "      # BEGIN GENERATED BUTTON PACKAGES\n"
                + entries +
                "      # END GENERATED BUTTON PACKAGES\n"
                "      - common/addon/time.yaml\n")

    def build(block_content, slots=2, ref_template="button_template_4chunk.yaml",
              with_markers=True):
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(os.path.join(tmp, "community"))
        dev = os.path.join(tmp, "devices", "dev-a")
        os.makedirs(dev)
        ref = os.path.join(tmp, "asm", "devices",
                           "guition-esp32-s3-4848s040")
        os.makedirs(ref)
        os.makedirs(os.path.join(tmp, "asm", "devices"), exist_ok=True)
        with open(os.path.join(tmp, "community", "devices.json"),
                  "w") as f:
            json.dump({"devices": ["dev-a"]}, f)
        with open(os.path.join(tmp, "community",
                               "catalog-fragment.json"), "w") as f:
            json.dump({"devices": {"dev-a": {
                "profiles": {"platform": "esp32-s3"}}}}, f)
        with open(os.path.join(tmp, "asm", "devices",
                               "manifest.json"), "w") as f:
            json.dump({"devices": {"dev-a": {"slots": slots}}}, f)
        with open(os.path.join(ref, "packages.yaml"), "w") as f:
            f.write(f"btn_1: !include {{ file: "
                    f"../../common/config/{ref_template}, "
                    f"vars: {{ num: \"1\" }} }}\n")
        content = block_content
        if not with_markers:
            content = content.replace(
                "      # BEGIN GENERATED BUTTON PACKAGES\n", "").replace(
                "      # END GENERATED BUTTON PACKAGES\n", "")
        with open(os.path.join(dev, "packages.yaml"), "w") as f:
            f.write(content)
        return check(tmp, os.path.join(tmp, "asm"))

    ok = community_block("button_template_4chunk.yaml", 2)
    if build(ok):
        failures.append(f"matching block reported drift: {build(ok)}")
    problems = build(community_block("button_template_4chunk.yaml", 3))
    if not any("drifted" in p for p in problems):
        failures.append(f"count drift not caught: {problems}")
    problems = build(community_block("button_template.yaml", 2))
    if not any("drifted" in p for p in problems):
        failures.append(f"template drift not caught: {problems}")
    problems = build(ok, with_markers=False)
    if not any("markers not found" in p for p in problems):
        failures.append(f"missing markers not caught: {problems}")

    shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        for msg in failures:
            print(f"[check_generated_blocks] self-test FAIL: {msg}",
                  file=sys.stderr)
        return 1
    print("[check_generated_blocks] self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(self_test())

    problems = check()
    if problems:
        print("Generated-block drift found:", file=sys.stderr)
        for msg in problems:
            print(f"  ✗ {msg}", file=sys.stderr)
        sys.exit(1)
    print("Generated blocks match generator output at the pin.")


if __name__ == "__main__":
    main()
