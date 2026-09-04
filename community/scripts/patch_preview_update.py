#!/usr/bin/env python3
"""
patch_preview_update.py – Stop a -preview build's update entity from ever
auto-downgrading a device to the stable release (issue #106).

Every device's packages.yaml points its ESPHome `update:` entity at
firmware/<slug>/manifest.json on Pages, which is staged from the latest
STABLE release only (community-pages.yml, so nothing auto-upgrades a device
onto a preview, per #99). ESPHome's http_request update component decides
"update available" by STRING INEQUALITY, not version ordering
(http_request/update/http_request_update.cpp), so a preview's version string
(e.g. v0.6.1-upstream.v2.8.4-preview.1) never matches that manifest and is
always reported as an update — even when the stable release is actually
OLDER. With auto-updates on by default, a panel deliberately put on a
preview silently reverts to stable. Worse: if Home Assistant has already
provisioned a Noise key for the device (it does this automatically once a
build advertises api_encryption_provisionable), reverting to a
pre-encryption stable build leaves the device unable to answer HA's Noise
hello at all, and it goes unavailable until someone clears the stored key.

The fix pins a preview build's compiled update entity at this exact
release's own manifest — same GitHub Release, uploaded as a
<slug>-manifest.json asset in the same release-creation step that assembles
$TAG — whose `version` field is generated from the identical $VERSION baked
into the firmware (generate_manifest.py). So latest_version ==
current_version forever and no update is ever reported. As a second,
independent guard (not relied on for correctness — with the source pinned
no update is ever detected regardless), the auto-update switch is also
forced off, so Home Assistant and the on-device GUI show it OFF rather than
defaulting on and quietly doing nothing.

This never touches the checked-in devices/<slug>/packages.yaml: it is run
by community-release.yml, for -preview tags only, against the *assembled*
copy under .assembly/ right before that device compiles.

Usage:
    python3 community/scripts/patch_preview_update.py <slug> --tag <tag> \
        [--repo-root <path>]
    python3 community/scripts/patch_preview_update.py --self-test
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_manifest import REPO_URL  # noqa: E402  (sibling script)

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

PREFIX = "[patch_preview_update]"

# The exact override line convert_packages.py writes into every device's
# packages.yaml (COMMUNITY_OVERRIDES). Matched literally, not loosely, so a
# future change to that template fails loudly here instead of silently
# leaving a preview build unpinned.
SOURCE_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*source:[ \t]*)"
    r"https://lamiskin\.github\.io/espcontrol-community-devices/firmware/"
    r"\$\{firmware_manifest_slug\}/manifest\.json[ \t]*$",
    re.MULTILINE,
)

SWITCH_OVERRIDE_MARKER = "id: !extend auto_update_switch"

SWITCH_OVERRIDE_BLOCK = """
# --- preview build: update entity pinned, issue #106 ---
# Second, independent guard on top of the pinned source above: force the
# auto-update switch off so Home Assistant / the on-device GUI show it OFF
# rather than defaulting on and silently doing nothing.
switch:
  - id: !extend auto_update_switch
    restore_mode: ALWAYS_OFF
"""


def error(msg):
    print(f"{PREFIX} ERROR: {msg}", file=sys.stderr)


def release_manifest_url(tag, slug):
    return f"{REPO_URL}/releases/download/{tag}/{slug}-manifest.json"


def packages_yaml_path(slug, repo_root=None):
    root = repo_root or REPO_ROOT
    return os.path.join(root, "devices", slug, "packages.yaml")


def patch(content, slug, tag):
    """
    Return `content` with its update.source pinned to this release's own
    manifest and its auto-update switch forced off. Raises ValueError if the
    expected template shape isn't found exactly once, or if it looks like
    this file has already been patched.
    """
    if SWITCH_OVERRIDE_MARKER in content:
        raise ValueError(
            f"'{slug}': packages.yaml already has an auto_update_switch "
            f"override — refusing to patch twice")

    new_source = release_manifest_url(tag, slug)
    patched, count = SOURCE_LINE_RE.subn(
        lambda m: f"{m.group('indent')}{new_source}", content)
    if count != 1:
        raise ValueError(
            f"'{slug}': expected exactly one update.source line matching "
            f"the Pages manifest template, found {count} — "
            f"convert_packages.py's COMMUNITY_OVERRIDES template may have "
            f"changed; update patch_preview_update.py to match")

    return patched.rstrip("\n") + "\n" + SWITCH_OVERRIDE_BLOCK


def self_test():
    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    fixture = """\
substitutions:
  firmware_manifest_slug: "demo-panel"
  firmware_version: "dev"

packages:
  device: !include device/device.yaml

update:
  - id: !extend firmware_update
    source: https://lamiskin.github.io/espcontrol-community-devices/firmware/${firmware_manifest_slug}/manifest.json
"""

    out = patch(fixture, "demo-panel", "community-v1.2.3-preview.1")
    expected_url = (f"{REPO_URL}/releases/download/"
                     "community-v1.2.3-preview.1/demo-panel-manifest.json")
    check("source line not pinned to the release manifest",
          f"    source: {expected_url}" in out)
    check("old Pages manifest URL still present",
          "lamiskin.github.io" not in out)
    check("auto-update switch override missing",
          "id: !extend auto_update_switch" in out
          and "restore_mode: ALWAYS_OFF" in out)
    check("update.source's own !extend block was disturbed",
          "id: !extend firmware_update" in out)

    try:
        patch("no update block here", "demo-panel", "t")
        failures.append("missing source line did NOT raise")
    except ValueError:
        pass

    try:
        patch(fixture + fixture, "demo-panel", "t")
        failures.append("duplicate source line did NOT raise")
    except ValueError:
        pass

    try:
        patch(out, "demo-panel", "t")
        failures.append("re-patching an already-patched file did NOT raise")
    except ValueError:
        pass

    # Every real device's checked-in packages.yaml must match the template
    # this script depends on, so drift is caught in CI rather than at
    # release time on a live preview tag.
    devices_dir = os.path.join(REPO_ROOT, "devices")
    if os.path.isdir(devices_dir):
        for slug in sorted(os.listdir(devices_dir)):
            path = packages_yaml_path(slug)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as f:
                real_content = f.read()
            try:
                patch(real_content, slug, "community-v0.0.0-preview.1")
            except ValueError as exc:
                failures.append(f"real device '{slug}': {exc}")

    if failures:
        for msg in failures:
            error(f"self-test: {msg}")
        return 1
    print(f"{PREFIX} self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", nargs="?")
    parser.add_argument("--tag", help="release tag, e.g. community-v1.2.3-upstream.vX-preview.1")
    parser.add_argument("--repo-root",
                        help="repo root containing devices/<slug>/packages.yaml "
                             "(defaults to this checkout; pass the assembly "
                             "dir to patch the compiled copy)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    missing = [n for n, v in (("slug", args.slug), ("--tag", args.tag)) if not v]
    if missing:
        parser.error(f"missing required arguments: {', '.join(missing)}")

    path = packages_yaml_path(args.slug, args.repo_root)
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        error(f"cannot read {path}: {exc}")
        sys.exit(1)

    try:
        patched = patch(content, args.slug, args.tag)
    except ValueError as exc:
        error(str(exc))
        sys.exit(1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(patched)

    print(f"{PREFIX} {args.slug}: pinned update.source to this release's "
          f"manifest and forced auto-update off")


if __name__ == "__main__":
    main()
