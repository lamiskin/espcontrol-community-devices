#!/usr/bin/env python3
"""
stage_recovery_manifests.py – Stage firmware/<slug>/recovery-manifest.json
onto Pages from a release's downloaded manifest assets (issue #98).

Companion to stage_firmware.py, which stages the regular
firmware/<slug>/manifest.json (the device's own update entity, always
present). A recovery manifest only exists for the P4 devices that carry a
builds/<slug>.recovery.yaml, and — unlike the regular manifest — it is
never load-bearing for a release: a device missing its recovery manifest
this deploy just means the "Repair C6 & reinstall firmware" button on its
docs page 404s until the next release builds one, not a broken update
feed. So this is entirely best-effort: nothing here can fail the deploy.

Usage:
    python3 community/scripts/stage_recovery_manifests.py \
        --assets release-assets --dest community-pages/firmware
    python3 community/scripts/stage_recovery_manifests.py --self-test
"""

import argparse
import json
import os
import shutil
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

PREFIX = "[stage_recovery_manifests]"


def warn(msg):
    print(f"{PREFIX} WARNING: {msg}", file=sys.stderr)


def load_registered(repo_root=None):
    root = repo_root or REPO_ROOT
    path = os.path.join(root, "community", "devices.json")
    with open(path, encoding="utf-8") as f:
        return list(json.load(f).get("devices", []))


def available_recovery_slugs(assets_dir):
    """Slugs with a <slug>-recovery-manifest.json in the downloaded assets."""
    if not os.path.isdir(assets_dir):
        return set()
    suffix = "-recovery-manifest.json"
    return {name[: -len(suffix)] for name in os.listdir(assets_dir)
            if name.endswith(suffix)}


def stage(registered, assets_dir, dest_dir):
    """Copy each registered slug's recovery manifest, if it built one."""
    staged = []
    for slug in registered:
        src = os.path.join(assets_dir, f"{slug}-recovery-manifest.json")
        if not os.path.isfile(src):
            continue
        out_dir = os.path.join(dest_dir, slug)
        os.makedirs(out_dir, exist_ok=True)
        shutil.copyfile(src, os.path.join(out_dir, "recovery-manifest.json"))
        staged.append(slug)
        print(f"{PREFIX} staged {slug}/recovery-manifest.json")
    return staged


def run(assets_dir, dest_dir, repo_root=None):
    registered = load_registered(repo_root)
    available = available_recovery_slugs(assets_dir)

    unregistered = available - set(registered)
    for slug in sorted(unregistered):
        warn(f"'{slug}-recovery-manifest.json' matches no device in "
             f"devices.json — not published")

    staged = stage(registered, assets_dir, dest_dir)
    if not staged:
        print(f"{PREFIX} no recovery manifests to stage")
    return staged


def self_test():
    import tempfile

    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix="stage_recovery_manifests_test_") as tmp:
        root = os.path.join(tmp, "repo")
        os.makedirs(os.path.join(root, "community"))
        with open(os.path.join(root, "community", "devices.json"), "w") as f:
            json.dump({"devices": ["p4-alpha", "s3-beta"]}, f)

        assets = os.path.join(tmp, "assets")
        os.makedirs(assets)
        # p4-alpha built a recovery manifest; s3-beta (not P4) never does;
        # a stray asset for a slug not in devices.json must be ignored.
        with open(os.path.join(assets, "p4-alpha-recovery-manifest.json"), "w") as f:
            json.dump({"name": "P4 Alpha — C6 Recovery", "version": "v1"}, f)
        with open(os.path.join(assets, "ghost-recovery-manifest.json"), "w") as f:
            json.dump({"name": "Ghost — C6 Recovery"}, f)

        dest = os.path.join(tmp, "firmware")
        staged = run(assets, dest, repo_root=root)

        check("p4-alpha not staged", staged == ["p4-alpha"])
        check("s3-beta got a recovery manifest it never built",
              not os.path.exists(os.path.join(dest, "s3-beta")))
        check("ghost asset was staged despite not being a real device",
              not os.path.exists(os.path.join(dest, "ghost")))

        out_path = os.path.join(dest, "p4-alpha", "recovery-manifest.json")
        check("recovery-manifest.json missing", os.path.isfile(out_path))
        if os.path.isfile(out_path):
            with open(out_path) as f:
                written = json.load(f)
            check("staged content wrong", written["version"] == "v1")

        # No assets at all (e.g. a release with no recovery-eligible
        # devices) must not error.
        empty_dest = os.path.join(tmp, "firmware2")
        staged2 = run(os.path.join(tmp, "nonexistent"), empty_dest, repo_root=root)
        check("empty assets dir was fatal or staged something",
              staged2 == [] and not os.path.exists(empty_dest))

    if failures:
        for msg in failures:
            print(f"{PREFIX} self-test: {msg}", file=sys.stderr)
        return 1
    print(f"{PREFIX} self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", default="release-assets",
                        help="directory holding downloaded "
                             "*-recovery-manifest.json release assets")
    parser.add_argument("--dest", default="community-pages/firmware",
                        help="firmware tree to stage into")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    run(args.assets, args.dest)


if __name__ == "__main__":
    main()
