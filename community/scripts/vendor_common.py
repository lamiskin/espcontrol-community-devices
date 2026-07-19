#!/usr/bin/env python3
"""
vendor_common.py – Vendor the upstream `common/` files that device YAML
references with filesystem-relative includes (`../../../common/...`).

Why this exists: end users install via an ESPHome remote package that clones
ONLY this repository. Remote packages in devices/<slug>/packages.yaml fetch
most upstream config over git, but `!include` lines nested inside device files
(font glyph lists, core_infra, button_widget) resolve against the local
filesystem of the clone. Those files must therefore exist in this repo at
`common/`, byte-identical to upstream at the pinned ref.

The vendored files are managed exclusively by this script. CI runs `--check`
to fail any PR where they drift from the pin; the ref-bump workflow runs the
default (write) mode to refresh them when the pin changes.

Usage:
    python3 community/scripts/vendor_common.py --source .assembly
    python3 community/scripts/vendor_common.py --source .assembly --check
    python3 community/scripts/vendor_common.py --self-test

`--source` is a checkout of upstream at the pinned ref (the assemble script's
`.assembly/` tree in CI). The pin recorded in the manifest comes from
community/upstream-ref.txt.
"""

import argparse
import hashlib
import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
PIN_FILE = os.path.join(REPO_ROOT, "community", "upstream-ref.txt")
MANIFEST_PATH = os.path.join(REPO_ROOT, "common", "VENDOR_MANIFEST.json")

INCLUDE_RE = re.compile(r'\.\./\.\./\.\./(common/[A-Za-z0-9_./-]+\.yaml)')
NESTED_INCLUDE_RE = re.compile(
    r'!include\s+(?:\{\s*file:\s*)?([A-Za-z0-9_./-]+\.yaml)'
)


def status(msg):
    print(f"[vendor_common] {msg}")


def error(msg):
    print(f"[vendor_common] ERROR: {msg}", file=sys.stderr)


def read_pin(repo_root=None):
    pin_file = PIN_FILE if repo_root is None else os.path.join(
        repo_root, "community", "upstream-ref.txt")
    with open(pin_file, "r", encoding="utf-8") as f:
        return f.read().strip()


def referenced_common_paths(repo_root=None):
    """Scan devices/**/*.yaml for ../../../common/... includes."""
    root = repo_root or REPO_ROOT
    devices_dir = os.path.join(root, "devices")
    paths = set()
    for dirpath, _dirnames, filenames in os.walk(devices_dir):
        for name in filenames:
            if not name.endswith(".yaml"):
                continue
            file_path = os.path.join(dirpath, name)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            for match in INCLUDE_RE.finditer(content):
                paths.add(match.group(1))
    return sorted(paths)


def transitive_guard(common_paths, source_dir):
    """
    Fail if any vendored file itself includes a file outside the vendored
    set — that file would be missing from user clones too.
    """
    problems = []
    vendored = set(common_paths)
    for rel_path in common_paths:
        src = os.path.join(source_dir, rel_path)
        if not os.path.isfile(src):
            continue
        with open(src, "r", encoding="utf-8") as f:
            content = f.read()
        base_dir = os.path.dirname(rel_path)
        for match in NESTED_INCLUDE_RE.finditer(content):
            target = os.path.normpath(
                os.path.join(base_dir, match.group(1)))
            if target.startswith("common/") and target not in vendored:
                problems.append(
                    f"{rel_path} includes {target}, which is not in the "
                    f"vendored set — add it by re-running vendor_common.py"
                )
    return problems


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def collect(source_dir, repo_root=None):
    """Return (common_paths, problems) after validating the source tree."""
    root = repo_root or REPO_ROOT
    problems = []
    common_paths = referenced_common_paths(root)
    if not common_paths:
        problems.append("no ../../../common/ references found under devices/")
        return common_paths, problems
    for rel_path in common_paths:
        if not os.path.isfile(os.path.join(source_dir, rel_path)):
            problems.append(f"missing in --source tree: {rel_path}")
    problems.extend(transitive_guard(common_paths, source_dir))
    return common_paths, problems


def vendor(source_dir, repo_root=None, check_only=False):
    """Vendor (or verify) the referenced common files. Returns exit code."""
    root = repo_root or REPO_ROOT
    manifest_path = os.path.join(root, "common", "VENDOR_MANIFEST.json")
    pin = read_pin(root)

    common_paths, problems = collect(source_dir, root)
    if problems:
        for p in problems:
            error(p)
        return 1

    if check_only:
        failures = []
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except FileNotFoundError:
            error(f"manifest not found: {manifest_path} — run without "
                  f"--check to create the vendored files")
            return 1
        if manifest.get("pin") != pin:
            failures.append(
                f"manifest pin '{manifest.get('pin')}' != current pin "
                f"'{pin}' — re-run vendor_common.py after a ref bump")
        if sorted(manifest.get("files", {})) != common_paths:
            failures.append(
                "vendored file set differs from what devices reference — "
                "re-run vendor_common.py")
        for rel_path in common_paths:
            dest = os.path.join(root, rel_path)
            src = os.path.join(source_dir, rel_path)
            if not os.path.isfile(dest):
                failures.append(f"missing vendored file: {rel_path}")
                continue
            if sha256_of(dest) != sha256_of(src):
                failures.append(
                    f"vendored file differs from upstream at pin: "
                    f"{rel_path}")
        if failures:
            for msg in failures:
                error(msg)
            return 1
        status(f"OK — {len(common_paths)} vendored files match pin {pin}")
        return 0

    files_entry = {}
    for rel_path in common_paths:
        src = os.path.join(source_dir, rel_path)
        dest = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(src, "rb") as f_in, open(dest, "wb") as f_out:
            f_out.write(f_in.read())
        files_entry[rel_path] = sha256_of(dest)
        status(f"vendored {rel_path}")

    manifest = {
        "_comment": (
            "Generated by community/scripts/vendor_common.py — do not edit "
            "by hand. These files are byte-identical copies from upstream "
            "at the pinned ref, required so end-user clones can resolve "
            "device-file relative includes."
        ),
        "pin": pin,
        "files": files_entry,
    }
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    status(f"wrote {len(files_entry)} files + manifest at pin {pin}")
    return 0


def self_test():
    import shutil
    import tempfile

    failures = []
    tmp = tempfile.mkdtemp(prefix="vendor_common_test_")
    try:
        repo = os.path.join(tmp, "repo")
        source = os.path.join(tmp, "source")
        os.makedirs(os.path.join(repo, "community"))
        device_dir = os.path.join(repo, "devices", "test-dev", "device")
        os.makedirs(device_dir)
        os.makedirs(os.path.join(source, "common", "assets"))

        with open(os.path.join(repo, "community", "upstream-ref.txt"),
                  "w") as f:
            f.write("v0.0.1\n")
        with open(os.path.join(device_dir, "fonts.yaml"), "w") as f:
            f.write("glyphs: !include ../../../common/assets/g.yaml\n")
        with open(os.path.join(source, "common", "assets", "g.yaml"),
                  "w") as f:
            f.write("- a\n- b\n")

        # Write mode creates file + manifest
        rc = vendor(source, repo_root=repo)
        vendored = os.path.join(repo, "common", "assets", "g.yaml")
        manifest = os.path.join(repo, "common", "VENDOR_MANIFEST.json")
        if rc != 0 or not os.path.isfile(vendored):
            failures.append("write mode did not vendor the file")
        if not os.path.isfile(manifest):
            failures.append("write mode did not write manifest")

        # Check mode passes on identical content
        if vendor(source, repo_root=repo, check_only=True) != 0:
            failures.append("check mode failed on identical content")

        # Check mode fails on drift
        with open(vendored, "a") as f:
            f.write("- tampered\n")
        if vendor(source, repo_root=repo, check_only=True) == 0:
            failures.append("check mode passed on tampered file")
        rc = vendor(source, repo_root=repo)  # restore
        if vendor(source, repo_root=repo, check_only=True) != 0:
            failures.append("re-vendor did not restore check to green")

        # Check mode fails on pin mismatch
        with open(os.path.join(repo, "community", "upstream-ref.txt"),
                  "w") as f:
            f.write("v9.9.9\n")
        if vendor(source, repo_root=repo, check_only=True) == 0:
            failures.append("check mode passed on pin mismatch")
        with open(os.path.join(repo, "community", "upstream-ref.txt"),
                  "w") as f:
            f.write("v0.0.1\n")

        # Transitive guard: vendored file includes a non-vendored one
        with open(os.path.join(source, "common", "assets", "g.yaml"),
                  "w") as f:
            f.write("base: !include other.yaml\n")
        rc = vendor(source, repo_root=repo)
        if rc == 0:
            failures.append("transitive guard did not fire")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        for msg in failures:
            error(f"self-test: {msg}")
        return 1
    status("self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",
                        help="path to an upstream checkout at the pinned ref"
                             " (e.g. .assembly)")
    parser.add_argument("--check", action="store_true",
                        help="verify vendored files match the source tree")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())
    if not args.source:
        parser.error("--source is required (or use --self-test)")
    source_dir = os.path.abspath(args.source)
    if not os.path.isdir(os.path.join(source_dir, "common")):
        error(f"--source {source_dir} has no common/ directory — is it an "
              f"upstream checkout?")
        sys.exit(1)
    sys.exit(vendor(source_dir, check_only=args.check))


if __name__ == "__main__":
    main()
