#!/usr/bin/env python3
"""
Assemble the full espcontrol tree with community device overlays.

Builds a throwaway working tree at .assembly/ by:
1. Cloning upstream espcontrol at the pinned ref
2. Copying community device overlays into the tree
3. Merging the community catalog fragment into upstream's device catalog
4. Running upstream generators (manifest, slots, build devices)
5. Running upstream validators (manifest, matrix, profiles)
6. Building the web bundle (npm ci + build.py www)
7. Copying the bundle to community-pages/webserver/www.js

Usage:
    python3 community/scripts/assemble.py [--skip-checks] [--skip-web] [--sync-generated] [--strict] [--self-test]
    python3 community/scripts/assemble.py --self-test-offline

--strict makes a non-zero exit from an upstream generator fail the run.
Upstream's generators own the content between the BEGIN/END GENERATED
markers; when one of them dies, the device keeps its previous blocks and
every check still passes, so a compile against it proves nothing about the
new ref. The ref-bump workflow runs with --strict for that reason.
"""

import argparse
import difflib
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
PIN_SHA_FILE = os.path.join(COMMUNITY_DIR, "upstream-sha.txt")
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


def read_resolved_sha():
    """Read the resolved commit SHA for the pin, if one has been recorded.

    Written by community-ref-bump.yml alongside upstream-ref.txt, so a
    clone can target an immutable commit even when `pin` itself is a tag
    name. Tags can be deleted or repointed upstream (this happened: v2.8.5
    vanished from jtenniswood/espcontrol and took every device's nightly
    build down with it, see #122-#129); a resolved SHA can't be. Absent on
    older commits or local runs — callers fall back to cloning by tag.
    """
    if not os.path.isfile(PIN_SHA_FILE):
        return None
    sha = open(PIN_SHA_FILE).read().strip()
    return sha or None


def clone_upstream(pin):
    """Clone upstream at the pinned ref into .assembly/.

    Prefers the resolved commit SHA (community/upstream-sha.txt) over the
    `pin` tag name when both are available — see read_resolved_sha().
    """
    if os.path.isdir(ASSEMBLY_DIR):
        status("Removing existing .assembly/ ...")
        shutil.rmtree(ASSEMBLY_DIR)

    resolved_sha = None if is_sha(pin) else read_resolved_sha()
    fetch_ref = resolved_sha or pin

    if resolved_sha:
        status(f"Cloning upstream at {pin} (resolved: {fetch_ref}) ...")
    else:
        status(f"Cloning upstream at {pin} ...")

    if is_sha(fetch_ref):
        # For SHA refs: clone default branch, fetch the SHA, checkout
        run(["git", "clone", "--depth", "1", UPSTREAM_REPO, ASSEMBLY_DIR])
        run(["git", "fetch", "origin", fetch_ref], cwd=ASSEMBLY_DIR)
        run(["git", "checkout", fetch_ref], cwd=ASSEMBLY_DIR)
        if resolved_sha and not is_sha(pin):
            # Downstream tooling (check_include_parity.py) does
            # `git show <tag>:<path>` against this clone, expecting the
            # tag name itself to resolve as a git ref — true when cloning
            # by --branch, not when fetching a bare SHA. Recreate it
            # locally from the pinned SHA, so that still works if the tag
            # vanished upstream. The clone may already contain it (possibly
            # repointed), so replace it only in this disposable local clone.
            run(["git", "tag", "--force", pin, fetch_ref], cwd=ASSEMBLY_DIR)
    else:
        # For tags/branches: clone directly at that ref
        run(["git", "clone", "--depth", "1", "--branch", fetch_ref, UPSTREAM_REPO, ASSEMBLY_DIR])

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
            # `{slug}*` also matches a *longer* slug that starts with this
            # one — m5stack-esp32-p4-tab5 would otherwise swallow
            # m5stack-esp32-p4-tab5-v1's build files and then collide with
            # itself when the loop reached that device. Build files are
            # always `<slug>.yaml` or `<slug>.<profile>.yaml`, so require the
            # separator right after the slug.
            if not fname[len(slug):].startswith("."):
                continue
            dst_path = os.path.join(builds_dst, fname)
            if os.path.exists(dst_path):
                error(f"Collision: build file {fname} already exists in upstream")
            status(f"  builds/{fname} -> .assembly/builds/{fname}")
            shutil.copy2(build_file, dst_path)

    status("Overlay copy complete.")


def find_catalog_path():
    """
    Locate upstream's device catalog file. Moved from devices/catalog.json
    to product/v2/device_catalog.json as of v2.8.0; older pins (<= v2.7.x)
    still use the legacy path, so both are checked.
    """
    new_path = os.path.join(ASSEMBLY_DIR, "product", "v2", "device_catalog.json")
    if os.path.isfile(new_path):
        return new_path
    legacy_path = os.path.join(ASSEMBLY_DIR, "devices", "catalog.json")
    if os.path.isfile(legacy_path):
        return legacy_path
    error(f"Upstream device catalog not found at {new_path} or {legacy_path}")


def merge_catalog(slugs):
    """
    Merge community catalog-fragment.json into upstream's device catalog.

    Upstream catalog structure (discovered from v2.6.3, moved from
    devices/catalog.json to product/v2/device_catalog.json as of v2.8.0):
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

    catalog_path = find_catalog_path()

    status(f"Merging {len(fragment_devices)} device(s) into device_catalog.json ...")
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

    register_product_model_v2_pilots(fragment_devices)


CAMERA_SLUGS_RE = re.compile(
    r"^(CAMERA_SCREENSAVER_DEVICE_SLUGS\s*=\s*)\{([^}]*)\}\s*$", re.MULTILINE)
CAMERA_SUPPORTED_RE = re.compile(
    r'^\s*screensaver_camera_supported:\s*"(true|false)"\s*$', re.MULTILINE)


def camera_supported_slugs(slugs, devices_dir=None):
    """
    Community devices whose own packages.yaml says the firmware supports the
    camera screensaver (`screensaver_camera_supported: "true"`).
    """
    devices_dir = devices_dir or os.path.join(REPO_ROOT, "devices")
    supported = []
    for slug in slugs:
        path = os.path.join(devices_dir, slug, "packages.yaml")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as handle:
            match = CAMERA_SUPPORTED_RE.search(handle.read())
        if match and match.group(1) == "true":
            supported.append(slug)
    return supported


def patch_camera_screensaver_slugs(slugs, profiles_path=None, devices_dir=None):
    """
    Make the web configurator offer the camera screensaver on every community
    device whose firmware includes it.

    Upstream decides that in scripts/device_profiles.py: a device gets
    features.cameraScreensaver if it is an ESP32-P4 or its slug is in
    CAMERA_SCREENSAVER_DEVICE_SLUGS, and there is no catalog setting for it.
    The community's packages.yaml files choose the firmware side by hand
    (`screensaver_camera_supported`), so the two could disagree: a board could
    carry the camera code with no way to switch it on from the UI. Adding the
    supported slugs to upstream's set keeps the UI and the firmware on the
    same answer, with the substitution as the single source of truth.

    The edit is made to the throwaway upstream clone. If upstream changes that
    line the patch fails loudly rather than silently doing nothing.
    """
    profiles_path = profiles_path or os.path.join(ASSEMBLY_DIR, "scripts", "device_profiles.py")
    with open(profiles_path, encoding="utf-8") as handle:
        source = handle.read()
    matches = CAMERA_SLUGS_RE.findall(source)
    if len(matches) != 1:
        error("Cannot make the web UI offer the camera screensaver: expected exactly one "
              "CAMERA_SCREENSAVER_DEVICE_SLUGS assignment in upstream's "
              f"scripts/device_profiles.py, found {len(matches)}. Upstream changed how "
              "that is decided; update patch_camera_screensaver_slugs().")
        sys.exit(1)
    existing = re.findall(r'"([^"]+)"', matches[0][1])
    wanted = camera_supported_slugs(slugs, devices_dir)
    merged = sorted(set(existing) | set(wanted))
    replacement = "CAMERA_SCREENSAVER_DEVICE_SLUGS = {" + ", ".join(f'"{s}"' for s in merged) + "}"
    patched = CAMERA_SLUGS_RE.sub(lambda m: replacement, source, count=1)
    if patched != source:
        with open(profiles_path, "w", encoding="utf-8") as handle:
            handle.write(patched)
    added = [s for s in merged if s not in existing]
    status(f"Camera screensaver offered in the web UI for {len(merged)} device(s) "
           f"({len(added)} added from packages.yaml).")
    return merged


def register_product_model_v2_pilots(fragment_devices):
    """
    Register each community device as a Product Model v2 "devices" pilot
    source.

    As of v2.8.0, upstream's generator/validator scripts load
    product/model_v2.json and, at its "generated-source" stage, require
    every product/v2/device_catalog.json entry to also exist as a
    standalone file under product/v2/devices/<slug>.json and be listed in
    model_v2.json's pilots.devices map — otherwise they raise
    ProductModelV2Error and refuse to run. Older upstream pins have no
    product/model_v2.json, so this is a no-op for them.
    """
    model_path = os.path.join(ASSEMBLY_DIR, "product", "model_v2.json")
    if not os.path.isfile(model_path):
        return

    model = json.loads(open(model_path).read())
    pilots = model.get("pilots")
    if not isinstance(pilots, dict) or "devices" not in pilots:
        return

    pilot_devices = pilots["devices"]
    devices_dir = os.path.join(ASSEMBLY_DIR, "product", "v2", "devices")
    os.makedirs(devices_dir, exist_ok=True)

    status(f"Registering {len(fragment_devices)} device(s) as Product Model v2 pilot sources ...")
    for slug, entry in fragment_devices.items():
        if slug in pilot_devices:
            error(f"Pilot collision: slug '{slug}' already exists in model_v2.json pilots.devices")
        pilot_path = os.path.join(devices_dir, f"{slug}.json")
        with open(pilot_path, "w") as f:
            json.dump(entry, f, indent=2)
            f.write("\n")
        pilot_devices[slug] = f"product/v2/devices/{slug}.json"
        status(f"  Registered pilot source for '{slug}'")

    with open(model_path, "w") as f:
        json.dump(model, f, indent=2)
        f.write("\n")

    status("Product Model v2 pilot registration complete.")


def block_key(begin_line):
    """
    Identity of a generated block: its BEGIN marker, whitespace-normalized.

    Upstream emits several distinct blocks per device (the button packages
    block, and four grid-wiring blocks), so a block in the assembly tree can
    only be matched to the same block in a source file by its marker —
    matching by position would silently swap one for another if a device
    gained or lost a block.
    """
    return re.sub(r"\s+", " ", begin_line.strip())


def parse_generated_blocks(content):
    """
    Parse the BEGIN/END GENERATED blocks out of file content.

    Returns a list of (start, end, key, text) tuples, one per block: start
    and end are 0-based line indices (end inclusive), key identifies the
    block by its BEGIN marker, and text is the block including its markers.
    """
    lines = content.splitlines(keepends=True)
    blocks = []
    i = 0
    while i < len(lines):
        if GENERATED_BEGIN_RE.search(lines[i]):
            end = i + 1
            while end < len(lines) and not GENERATED_END_RE.search(lines[end]):
                end += 1
            if end < len(lines):
                blocks.append((i, end, block_key(lines[i]),
                               "".join(lines[i:end + 1])))
                i = end + 1
                continue
        i += 1
    return blocks


def strip_generated_blocks(content):
    """File content with every generated block removed."""
    lines = content.splitlines(keepends=True)
    skip = set()
    for start, end, _key, _text in parse_generated_blocks(content):
        skip.update(range(start, end + 1))
    return "".join(line for i, line in enumerate(lines) if i not in skip)


def diff_ignoring_generated(old_content, new_content):
    """
    Check if two file contents differ outside of generated blocks.
    Returns True if there are meaningful (non-generated) differences.
    """
    return strip_generated_blocks(old_content) != strip_generated_blocks(new_content)


def splice_generated_blocks(source_content, assembly_content):
    """
    Replace each generated block in source_content with the matching block
    from assembly_content.

    Blocks are matched by their BEGIN marker, so a block that exists on
    only one side is left alone rather than shifting everything after it.

    Returns (new_content, changed_block_count, unmatched_keys).
    """
    assembly_blocks = {}
    for _start, _end, key, text in parse_generated_blocks(assembly_content):
        assembly_blocks[key] = text

    lines = source_content.splitlines(keepends=True)
    out = []
    pos = 0
    changed = 0
    unmatched = []
    for start, end, key, text in parse_generated_blocks(source_content):
        if key not in assembly_blocks:
            unmatched.append(key)
            continue
        replacement = assembly_blocks[key]
        out.extend(lines[pos:start])
        out.append(replacement)
        pos = end + 1
        if replacement != text:
            changed += 1
    out.extend(lines[pos:])
    return "".join(out), changed, unmatched


def print_unified_diff(old_desc, new_desc, old_content, new_content,
                       max_lines=40):
    """
    Print a bounded unified diff.

    The files involved are whole device packages — a full diff runs to
    hundreds of lines and buries the part that matters, so it is truncated
    with an explicit note about what was left out.
    """
    diff = list(difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{old_desc}",
        tofile=f"b/{new_desc}",
    ))
    if not diff:
        return
    print(f"\n--- {old_desc} (community, hand-maintained)")
    print(f"+++ {new_desc} (upstream generator output)")
    for line in diff[:max_lines]:
        print(line.rstrip("\n"))
    if len(diff) > max_lines:
        print(f"  … diff truncated ({len(diff) - max_lines} more lines)")


def sync_file_blocks(src_path, asm_path, label=None):
    """
    Copy the generated blocks from the assembly file into the source file.

    Only content between BEGIN/END GENERATED markers is copied. When the
    generator changed anything outside those markers, the source file is
    left untouched and "refused" is returned: upstream's generator rewrites
    a device's whole packages.yaml into its own relative-include form, and
    copying that back would drop the remote include pins, the community
    substitutions and the ui= cache stamp — all hand-maintained here and
    none of them something the generator understands.

    Returns (outcome, detail) where outcome is "unchanged", "written" or
    "refused".
    """
    asm_content = open(asm_path).read()
    src_content = open(src_path).read()
    if asm_content == src_content:
        return "unchanged", "identical"

    if diff_ignoring_generated(src_content, asm_content):
        if label:
            print_unified_diff(label, f".assembly/{label}",
                               src_content, asm_content)
        return "refused", "the generator changed content outside the generated blocks"

    new_content, changed, unmatched = splice_generated_blocks(src_content,
                                                              asm_content)
    if unmatched:
        if label:
            print_unified_diff(label, f".assembly/{label}",
                               src_content, asm_content)
        return "refused", ("no counterpart in the assembly tree for: "
                           + ", ".join(unmatched))
    if new_content == src_content:
        return "unchanged", "identical"

    with open(src_path, "w") as f:
        f.write(new_content)
    return "written", f"{changed} generated block(s)"


def sync_generated_back(slugs):
    """
    Copy generated blocks from .assembly/devices/<slug>/ back to the source
    devices/<slug>/ in the repo root.

    Only the content inside the BEGIN/END GENERATED markers is copied, and
    a file the generator rewrote outside those markers is refused rather
    than overwritten — see sync_file_blocks().

    Returns (written_paths, refused_paths).
    """
    written = []
    refused = []
    if not slugs:
        return written, refused

    status("Syncing generated blocks back to source ...")
    for slug in slugs:
        assembly_device = os.path.join(ASSEMBLY_DIR, "devices", slug)
        source_device = os.path.join(REPO_ROOT, "devices", slug)
        if not os.path.isdir(assembly_device) or not os.path.isdir(source_device):
            continue
        for root, _dirs, files in os.walk(assembly_device):
            for fname in sorted(files):
                asm_path = os.path.join(root, fname)
                rel_path = os.path.relpath(asm_path, assembly_device)
                src_path = os.path.join(source_device, rel_path)
                if not os.path.isfile(src_path):
                    continue
                label = f"devices/{slug}/{rel_path}"
                outcome, detail = sync_file_blocks(src_path, asm_path, label)
                if outcome == "written":
                    written.append(label)
                    status(f"  Synced {detail} into {label}")
                elif outcome == "refused":
                    refused.append(label)
                    status(f"  REFUSED {label}: {detail}")
    return written, refused


def run_generators(slugs, sync_generated=False, strict=False):
    """
    Run upstream generator scripts inside .assembly/.

    With strict=True a generator that exits non-zero fails the run. The
    generators own the content between the BEGIN/END GENERATED markers, so
    a dead one leaves the device on the blocks it had before the ref bump:
    everything downstream still passes, and the compiled firmware is a mix
    of two upstream versions.
    """
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

    failures = []
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
            failures.append((cmd, result.returncode))
            status(f"  Generator FAILED: '{' '.join(cmd)}' exited with code {result.returncode}")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            status("  The generated blocks of the affected devices are STALE "
                   "at this ref — a compile against them proves nothing.")

    if failures:
        summary = ", ".join(f"{' '.join(cmd)} (exit {code})"
                            for cmd, code in failures)
        if strict:
            error(f"{len(failures)} upstream generator(s) failed: {summary}. "
                  "Refusing to continue: the generated blocks would be stale.")
        status(f"  (Continuing — generator failure may require extra "
               f"dependencies) [{len(failures)} generator(s) failed: {summary}]")

    # generate_device_slots.py rewrites the whole packages section of any
    # file carrying the generated-block markers into upstream relative-
    # include form — with the default button template, which is wrong for
    # community devices. That rewrite is unwanted here: assembly compiles
    # must use the true remote-include form users get. Sync generated
    # blocks back first if requested (block content only — a file the
    # generator rewrote outside the markers is refused, not overwritten),
    # then restore the community sources.
    if slugs:
        if sync_generated:
            written, refused = sync_generated_back(slugs)
            if refused:
                status(f"ERROR: {len(refused)} file(s) refused — the generator "
                       "rewrote hand-maintained content outside the generated "
                       "blocks:")
                for path in refused:
                    status(f"  - {path}")
                if strict:
                    error("Refusing to sync generated blocks into files the "
                          "generator rewrote wholesale. Reconcile them by hand.")
        for slug in slugs:
            src = os.path.join(REPO_ROOT, "devices", slug, "packages.yaml")
            dst = os.path.join(ASSEMBLY_DIR, "devices", slug,
                               "packages.yaml")
            if os.path.isfile(src) and os.path.isfile(dst):
                shutil.copyfile(src, dst)

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

    status("Generators complete.")


def build_web_bundle(skip=False):
    """Build the web bundle (www.js) from the assembled tree.

    Runs npm ci + build.py www inside .assembly/, then copies the
    resulting bundle to community-pages/webserver/www.js.
    """
    if skip:
        status("Skipping web bundle build (--skip-web).")
        return

    status("Building web bundle ...")

    # npm ci to install node dependencies
    run(["npm", "ci"], cwd=ASSEMBLY_DIR)

    # build.py www produces docs/public/webserver/www.js
    run(["python3", "scripts/build.py", "www"], cwd=ASSEMBLY_DIR)

    # Locate the bundle. As of v2.8.0, docs/public/webserver/www.js is a
    # small "bridge" loader that fetches a device/version-matched bundle at
    # runtime via web-assets.json — it has no GUI content of its own and
    # depends on endpoints a live ESPHome device serves, which community's
    # statically-hosted community-pages/webserver/www.js can't provide.
    # docs/public/webserver/embedded/www.js is the self-contained successor
    # (same role the old monolithic www.js used to play), so it's preferred
    # when present; older pins without the split fall back to the flat path.
    webserver_dir = os.path.join(ASSEMBLY_DIR, "docs", "public", "webserver")
    bundle_path = os.path.join(webserver_dir, "embedded", "www.js")

    if not os.path.isfile(bundle_path):
        bundle_path = os.path.join(webserver_dir, "www.js")

    if not os.path.isfile(bundle_path):
        # Fallback: search for www.js under docs/
        for root, _dirs, files in os.walk(
            os.path.join(ASSEMBLY_DIR, "docs")
        ):
            if "www.js" in files:
                bundle_path = os.path.join(root, "www.js")
                break

    if not os.path.isfile(bundle_path):
        error("Web bundle not found after build.py www")

    status(
        f"Bundle found: "
        f"{os.path.relpath(bundle_path, ASSEMBLY_DIR)}"
    )

    # Copy to community-pages/webserver/www.js
    output_dir = os.path.join(
        REPO_ROOT, "community-pages", "webserver"
    )
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "www.js")
    shutil.copy2(bundle_path, output_path)

    # Community post-processing: rewrite user-facing upstream links to the
    # community docs/firmware and inject the unofficial-build banner.
    # Fails loudly if upstream's web GUI links changed at this pin.
    run(["python3",
         os.path.join(REPO_ROOT, "community", "scripts",
                      "postprocess_www.py"),
         output_path])

    # Factory builds embed the bundle with
    # `js_include: ../community-pages/webserver/www.js`, resolved relative to
    # .assembly/builds/ — so they need it inside the assembly tree, not just at
    # the repo root. Copy the post-processed bundle across here rather than
    # leaving each workflow to remember: community-release.yml did, the nightly
    # factory step added in #79 did not, and every device that embeds the
    # bundle failed config until this landed.
    assembly_output_dir = os.path.join(
        ASSEMBLY_DIR, "community-pages", "webserver"
    )
    os.makedirs(assembly_output_dir, exist_ok=True)
    shutil.copy2(output_path,
                 os.path.join(assembly_output_dir, "www.js"))

    size = os.path.getsize(output_path)
    status(
        f"Bundle copied to community-pages/webserver/www.js "
        f"and .assembly/community-pages/webserver/www.js "
        f"({size} bytes)"
    )


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



def self_test_offline():
    """
    Self-tests that need no upstream clone and no network.

    They cover the rule that keeps --sync-generated from destroying
    hand-maintained content: upstream's generator rewrites a device's whole
    packages.yaml into its own relative-include form, dropping the remote
    include pins, the community substitutions and the ui= cache stamp, so a
    file it rewrote outside the generated markers has to be refused rather
    than overwritten.

    Returns 0 on success, 1 on failure.
    """
    import shutil
    import tempfile

    failures = []

    source = (
        "substitutions:\n"
        "  voice_clock_bar_apply_code: \"\"\n"
        "packages:\n"
        "  upstream_c:\n"
        "    files:\n"
        "      # BEGIN GENERATED BUTTON PACKAGES\n"
        "      - path: common/config/button_template.yaml\n"
        "      # END GENERATED BUTTON PACKAGES\n"
        "      - common/addon/time.yaml\n"
        "web_server:\n"
        "  js_url: https://example.test/www.js?v=1&ui=abc123\n"
    )
    assembly = source.replace(
        "      - path: common/config/button_template.yaml\n",
        "      - path: common/config/button_template.yaml\n"
        "        vars: { num: \"1\" }\n"
        "        vars: { num: \"2\" }\n",
    )
    rewritten = source.replace(
        "- common/addon/time.yaml\n", "- common/addon/other.yaml\n")

    tmp = tempfile.mkdtemp(prefix="assemble_sync_test_")
    try:
        src_path = os.path.join(tmp, "packages.yaml")
        asm_path = os.path.join(tmp, "packages.assembly.yaml")

        # 1. A change confined to the generated markers is spliced in, and
        #    everything outside them survives byte-for-byte.
        with open(src_path, "w") as f:
            f.write(source)
        with open(asm_path, "w") as f:
            f.write(assembly)
        outcome, detail = sync_file_blocks(src_path, asm_path)
        if outcome != "written":
            failures.append(f"expected the block change to be written, got "
                            f"{outcome} ({detail})")
        with open(src_path) as f:
            spliced = f.read()
        if 'vars: { num: "2" }' not in spliced:
            failures.append("the generated block was not spliced in")
        for keep in ('voice_clock_bar_apply_code: ""', "ui=abc123",
                     "- common/addon/time.yaml"):
            if keep not in spliced:
                failures.append(f"hand-maintained content lost: {keep}")
        if diff_ignoring_generated(source, spliced):
            failures.append("splicing changed content outside the generated "
                            "blocks")

        # 2. The generator rewriting the file wholesale is refused, and the
        #    hand-maintained content is left exactly as it was.
        with open(src_path, "w") as f:
            f.write(source)
        with open(asm_path, "w") as f:
            f.write(rewritten)
        outcome, detail = sync_file_blocks(src_path, asm_path)
        if outcome != "refused":
            failures.append(f"expected the wholesale rewrite to be refused, "
                            f"got {outcome}")
        with open(src_path) as f:
            after = f.read()
        if after != source:
            failures.append("a refused file was modified anyway")

        # 3. Blocks are matched by their marker, not by position: a block
        #    only the source has stays put, and the block after it is still
        #    the one that gets replaced.
        two_blocks = (
            "# BEGIN GENERATED A\n"
            "a-old\n"
            "# END GENERATED A\n"
            "keep me\n"
            "# BEGIN GENERATED B\n"
            "b-old\n"
            "# END GENERATED B\n"
        )
        only_b = (
            "# BEGIN GENERATED B\n"
            "b-new\n"
            "# END GENERATED B\n"
        )
        new_content, changed, unmatched = splice_generated_blocks(two_blocks,
                                                                  only_b)
        if "a-old" not in new_content:
            failures.append("a block with no counterpart was dropped")
        if "b-new" not in new_content:
            failures.append("the block after an unmatched one was not replaced")
        if changed != 1:
            failures.append(f"expected 1 changed block, got {changed}")
        if unmatched != ["# BEGIN GENERATED A"]:
            failures.append(f"unexpected unmatched blocks: {unmatched}")
        if "keep me" not in new_content:
            failures.append("content between blocks was lost")

        # 4. A rewrite outside the markers is detected, and a change inside
        #    them is not mistaken for one.
        if not diff_ignoring_generated(source, rewritten):
            failures.append("an outside-block rewrite was not detected")
        if diff_ignoring_generated(source, assembly):
            failures.append("a change inside the markers read as an "
                            "outside-block rewrite")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 4b. The web UI offers the camera screensaver exactly where the device's
    #     packages.yaml says the firmware has it, and the patch refuses to run
    #     against an upstream that changed how that is decided.
    tmp = tempfile.mkdtemp(prefix="assemble_camera_test_")
    try:
        devices_dir = os.path.join(tmp, "devices")
        for slug, flag in (("has-camera", "true"), ("no-camera", "false"), ("unset", None)):
            os.makedirs(os.path.join(devices_dir, slug))
            body = "substitutions:\n  device_slug: x\n"
            if flag is not None:
                body += f'  screensaver_camera_supported: "{flag}"\n'
            with open(os.path.join(devices_dir, slug, "packages.yaml"), "w") as handle:
                handle.write(body)
        profiles = os.path.join(tmp, "device_profiles.py")
        with open(profiles, "w") as handle:
            handle.write('X = 1\nCAMERA_SCREENSAVER_DEVICE_SLUGS = {"upstream-ref"}\nY = 2\n')
        slugs = ["has-camera", "no-camera", "unset", "missing-dir"]
        merged = patch_camera_screensaver_slugs(slugs, profiles, devices_dir)
        if merged != ["has-camera", "upstream-ref"]:
            failures.append(f"camera slugs should be upstream's plus the supported device, got {merged}")
        again = patch_camera_screensaver_slugs(slugs, profiles, devices_dir)
        with open(profiles) as handle:
            text = handle.read()
        if again != merged or text.count("CAMERA_SCREENSAVER_DEVICE_SLUGS") != 1 \
                or not text.startswith("X = 1\n") or not text.endswith("Y = 2\n"):
            failures.append("the camera slug patch is not idempotent or touched other lines")
        with open(profiles, "w") as handle:
            handle.write("X = 1\n")
        try:
            patch_camera_screensaver_slugs(slugs, profiles, devices_dir)
            failures.append("the camera slug patch did not fail when upstream's line is gone")
        except SystemExit:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 5. A function defined twice here is silently shadowed by its later
    #    definition. That is how a stale, overwrite-everything copy of
    #    sync_generated_back once survived next to the marker-scoped one and
    #    quietly replaced it, so the guard above was never in effect.
    import ast
    with open(os.path.abspath(__file__), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    defined = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    duplicates = sorted({name for name in defined if defined.count(name) > 1})
    if duplicates:
        failures.append(f"function(s) defined twice, the later one wins: {duplicates}")
    if sync_generated_back([]) != ([], []):
        failures.append("sync_generated_back must return (written, refused)")

    # 6. --strict turns a dead generator into a failed run; without it the
    #    failure is reported and the run continues, which is what let a ref
    #    bump report success while compiling stale device blocks.
    import contextlib
    import io
    import subprocess as real_subprocess

    class _DeadGenerator:
        returncode = 1
        stdout = ""
        stderr = "simulated generator failure\n"

    def fake_run(cmd, *args, **kwargs):
        return _DeadGenerator()

    original_run = real_subprocess.run
    real_subprocess.run = fake_run
    strict_failed = False
    try:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            run_generators([], strict=False)
            try:
                run_generators([], strict=True)
            except SystemExit as exc:
                strict_failed = exc.code in (1, None)
    finally:
        real_subprocess.run = original_run

    if not strict_failed:
        failures.append("--strict did not fail the run when a generator died")

    # 7. A clone may already contain the release tag. Keep both HEAD and
    #    the local parity-tooling tag on the immutable SHA, even if upstream
    #    has since repointed the tag. Exercise real Git without the network.
    from unittest import mock

    with tempfile.TemporaryDirectory(prefix="assemble_clone_test_") as tmp:
        upstream = os.path.join(tmp, "upstream")
        os.mkdir(upstream)

        def git(*args):
            return subprocess.run(
                ["git", *args], cwd=upstream, check=True,
                capture_output=True, text=True).stdout.strip()

        git("init", "--initial-branch=main")
        git("config", "user.name", "Assembly Test")
        git("config", "user.email", "assembly@example.invalid")
        git("config", "commit.gpgsign", "false")
        git("config", "tag.gpgsign", "false")
        git("commit", "--allow-empty", "-m", "Pinned commit")
        old_sha = git("rev-parse", "HEAD")
        git("commit", "--allow-empty", "-m", "Later commit")
        head_sha = git("rev-parse", "HEAD")
        pin = "v2.15.0"
        for case in ("missing", "existing", "annotated", "repointed"):
            if case == "annotated":
                git("tag", "--annotate", pin, "-m", "Release")
            elif case != "missing":
                git("tag", pin)
            expected_sha = old_sha if case == "repointed" else head_sha
            clone = os.path.join(tmp, case)
            with mock.patch.dict(globals(), {
                "UPSTREAM_REPO": "file://" + upstream,
                "ASSEMBLY_DIR": clone,
            }), mock.patch(__name__ + ".read_resolved_sha", return_value=expected_sha):
                try:
                    clone_upstream(pin)
                    for ref in ("HEAD", f"refs/tags/{pin}^{{commit}}"):
                        actual = subprocess.run(
                            ["git", "rev-parse", ref], cwd=clone, check=True,
                            capture_output=True, text=True).stdout.strip()
                        if actual != expected_sha:
                            failures.append(f"{case}: {ref} is not the pinned SHA")
                except SystemExit:
                    failures.append(f"{case}: cloning the pinned SHA failed")
            if case != "missing":
                git("tag", "--delete", pin)

    if failures:
        for msg in failures:
            print(f"[assemble] self-test: {msg}", file=sys.stderr)
        return 1
    print("[assemble] offline self-test passed")
    return 0


def run_self_test():
    """
    Self-test mode: verify the catalog merge logic works with the real
    upstream catalog structure using a fixture.
    """
    status("Running self-test ...")

    # The offline checks need no clone, so they run first: a failure there
    # is cheap to find and does not need the network.
    if self_test_offline() != 0:
        error("Offline self-tests failed")

    # Step 1: Read the pin and clone upstream
    pin = read_pin()
    clone_upstream(pin)

    # Step 2: Verify the clone has expected structure
    catalog_path = find_catalog_path()

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

    # Build-file globbing must not let one slug claim a longer slug's files.
    # devices/<a> and devices/<a>-v1 both exist in this repo, and the naive
    # f"{slug}*.yaml" glob made <a> copy <a>-v1's build files and then
    # collide with itself on the next iteration.
    status("Checking build-file glob is prefix-safe ...")
    build_tmp = tempfile.mkdtemp(prefix="assemble_glob_test_")
    try:
        base = "panel-x"
        variant = "panel-x-v1"
        names = [
            f"{base}.yaml", f"{base}.factory.yaml", f"{base}.recovery.yaml",
            f"{variant}.yaml", f"{variant}.factory.yaml",
        ]
        for n in names:
            open(os.path.join(build_tmp, n), "w").close()

        def matches(slug):
            found = []
            for path in glob.glob(os.path.join(build_tmp, f"{slug}*.yaml")):
                fname = os.path.basename(path)
                if not fname[len(slug):].startswith("."):
                    continue
                found.append(fname)
            return sorted(found)

        base_files = matches(base)
        variant_files = matches(variant)
        expected_base = sorted(
            [f"{base}.yaml", f"{base}.factory.yaml", f"{base}.recovery.yaml"])
        expected_variant = sorted([f"{variant}.yaml", f"{variant}.factory.yaml"])

        if base_files != expected_base:
            error(f"Self-test failed: '{base}' matched {base_files}, "
                  f"expected {expected_base}")
        if variant_files != expected_variant:
            error(f"Self-test failed: '{variant}' matched {variant_files}, "
                  f"expected {expected_variant}")
        if set(base_files) & set(variant_files):
            error("Self-test failed: base and variant globs overlap")
        status("  Build-file glob is prefix-safe.")
    finally:
        shutil.rmtree(build_tmp, ignore_errors=True)

    status("Self-test PASSED.")


def main():
    parser = argparse.ArgumentParser(description="Assemble espcontrol tree with community overlays")
    parser.add_argument("--skip-checks", action="store_true", help="Skip running validators")
    parser.add_argument("--skip-web", action="store_true", help="Skip web bundle build (requires node/npm)")
    parser.add_argument("--sync-generated", action="store_true", help="Copy generated blocks back to source")
    parser.add_argument("--strict", action="store_true",
                        help="Fail when an upstream generator exits non-zero "
                             "(default: warn and continue)")
    parser.add_argument("--self-test", action="store_true", help="Run self-test mode")
    parser.add_argument("--self-test-offline", action="store_true",
                        help="Run only the self-tests that need no upstream clone")
    args = parser.parse_args()

    if args.self_test_offline:
        sys.exit(self_test_offline())
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

    # Step 4b: Keep the web UI's camera screensaver in step with the firmware
    patch_camera_screensaver_slugs(slugs)

    # Step 5: Run generators
    run_generators(slugs, sync_generated=args.sync_generated, strict=args.strict)

    # Step 6: Run validators (unless --skip-checks)
    if not args.skip_checks:
        run_validators()
    else:
        status("Skipping validators (--skip-checks).")

    # Step 7: Build web bundle (unless --skip-web)
    build_web_bundle(skip=args.skip_web)

    status("Assembly complete. Tree is at .assembly/")


if __name__ == "__main__":
    main()
