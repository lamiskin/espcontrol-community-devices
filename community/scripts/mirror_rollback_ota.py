#!/usr/bin/env python3
"""
mirror_rollback_ota.py – Copy ota.bin onto Pages for a handful of releases
so the panel's web UI can install a *specific* version without hitting
GitHub's release-download CORS wall (issue #104).

The panel's "Previous firmware" rollback picker and preview installs work by
having the BROWSER download the .ota.bin (from versions.json's absolute
github.com/.../releases/download/... URL) and re-upload it to the device.
GitHub's release-download redirect does not carry
access-control-allow-origin, so the browser fetch is blocked before it
starts. Normal auto-updates are unaffected: the device fetches its own OTA
directly, and CORS is a browser-only restriction.

Deliberately narrow: every release served this way stops counting toward
the per-device download stats this project also cares about (39b32eb, which
moved binaries OFF Pages for exactly that reason) — so only whichever
releases are passed via --tags are mirrored, not the whole rollback list.
generate_versions_index.py's MAX_ENTRIES (5) already caps how many entries
even exist; this can cover fewer of them than that.

Run AFTER generate_versions_index.py has written firmware/<slug>/
versions.json: this script rewrites the ota.path of any entry whose release
tag is in --tags, and copies the matching
<assets-dir>/<tag>/<slug>.ota.bin release asset (already downloaded for the
history-index build) to firmware/<slug>/history/<tag>/<slug>.ota.bin so that
path resolves. manifest.json is never touched — it drives the device's own
update entity and must keep pointing at the real release asset, preserving
download-count accuracy for every normal install.

Usage:
    python3 community/scripts/mirror_rollback_ota.py \
        --assets-dir release-assets/history \
        --firmware-root community-pages/firmware \
        --tags <tag> [<tag> ...]
    python3 community/scripts/mirror_rollback_ota.py --self-test
"""

import argparse
import json
import os
import re
import shutil
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

SITE_URL = "https://lamiskin.github.io/espcontrol-community-devices"
REPO_URL = "https://github.com/lamiskin/espcontrol-community-devices"

PREFIX = "[mirror_rollback_ota]"

RELEASE_URL_RE = re.compile(
    r"^" + re.escape(REPO_URL) + r"/releases/tag/(?P<tag>.+)$")


def warn(msg):
    print(f"{PREFIX} WARNING: {msg}", file=sys.stderr)


def load_devices(repo_root=None):
    root = repo_root or REPO_ROOT
    path = os.path.join(root, "community", "devices.json")
    with open(path, encoding="utf-8") as f:
        return list(json.load(f).get("devices", []))


def tag_from_release_url(url):
    match = RELEASE_URL_RE.match(str(url or "").strip())
    return match.group("tag") if match else None


def pages_ota_path(slug, tag, site_url=SITE_URL):
    return f"{site_url}/firmware/{slug}/history/{tag}/{slug}.ota.bin"


def mirror_slug(slug, firmware_root, assets_dir, mirror_tags, site_url=SITE_URL):
    """
    Rewrite firmware/<slug>/versions.json in place, mirroring ota.bin for any
    entry whose release tag is in ``mirror_tags``. Returns (changed,
    warnings): ``changed`` is True if the file was rewritten.
    """
    warnings = []
    versions_path = os.path.join(firmware_root, slug, "versions.json")
    if not os.path.isfile(versions_path):
        return False, warnings

    with open(versions_path, encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    for entry in data.get("versions", []):
        ota = entry.get("ota")
        if not isinstance(ota, dict):
            continue
        path = str(ota.get("path", ""))
        if path.startswith(site_url):
            continue  # already mirrored by a previous run

        tag = tag_from_release_url(entry.get("release_url"))
        if tag is None or tag not in mirror_tags:
            continue

        src = os.path.join(assets_dir, tag, f"{slug}.ota.bin")
        if not os.path.isfile(src):
            warnings.append(
                f"'{slug}' {entry.get('version')}: no {src} — leaving its "
                f"rollback/preview web install CORS-blocked")
            continue

        dest_dir = os.path.join(firmware_root, slug, "history", tag)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, f"{slug}.ota.bin")
        shutil.copyfile(src, dest)

        ota["path"] = pages_ota_path(slug, tag, site_url)
        changed = True

    if changed:
        with open(versions_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    return changed, warnings


def run(firmware_root, assets_dir, mirror_tags, devices, site_url=SITE_URL):
    mirror_tags = set(mirror_tags)
    mirrored, warnings = [], []
    for slug in devices:
        changed, slug_warnings = mirror_slug(
            slug, firmware_root, assets_dir, mirror_tags, site_url)
        warnings.extend(slug_warnings)
        if changed:
            mirrored.append(slug)
    for msg in warnings:
        warn(msg)
    if mirrored:
        print(f"{PREFIX} mirrored ota.bin for: {', '.join(mirrored)}")
    else:
        print(f"{PREFIX} nothing to mirror "
              f"(no versions.json entries matched --tags)")
    return mirrored, warnings


def self_test():
    import tempfile

    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    def versions_doc(entries):
        return {"device": "demo", "versions": entries}

    def entry(version, tag, ota_path=None):
        return {
            "version": version,
            "release_url": f"{REPO_URL}/releases/tag/{tag}",
            "ota": {
                "path": ota_path or f"{REPO_URL}/releases/download/{tag}/demo.ota.bin",
                "md5": "0" * 32,
            },
        }

    with tempfile.TemporaryDirectory(prefix="mirror_rollback_ota_test_") as tmp:
        firmware_root = os.path.join(tmp, "firmware")
        assets_dir = os.path.join(tmp, "assets")

        # demo: one entry in the mirror set with a real asset, one in the
        # mirror set with a MISSING asset, one not in the mirror set at all.
        os.makedirs(os.path.join(firmware_root, "demo"), exist_ok=True)
        with open(os.path.join(firmware_root, "demo", "versions.json"), "w") as f:
            json.dump(versions_doc([
                entry("v1.2.0", "tag-new"),
                entry("v1.1.0", "tag-missing-asset"),
                entry("v1.0.0", "tag-old"),
            ]), f)

        os.makedirs(os.path.join(assets_dir, "tag-new"), exist_ok=True)
        with open(os.path.join(assets_dir, "tag-new", "demo.ota.bin"), "wb") as f:
            f.write(b"firmware-bytes")

        # no-versions-json: a slug with nothing staged yet must not error.
        os.makedirs(os.path.join(firmware_root, "no-versions-json"), exist_ok=True)

        mirrored, warnings = run(
            firmware_root, assets_dir,
            mirror_tags=["tag-new", "tag-missing-asset"],
            devices=["demo", "no-versions-json", "not-a-real-slug"])

        check("demo not reported as mirrored", mirrored == ["demo"])
        check("missing-asset entry did not warn as expected",
              any("tag-missing-asset" in w for w in warnings))

        with open(os.path.join(firmware_root, "demo", "versions.json")) as f:
            written = json.load(f)
        by_version = {e["version"]: e for e in written["versions"]}

        check("in-mirror-set entry not rewritten to a Pages URL",
              by_version["v1.2.0"]["ota"]["path"]
              == f"{SITE_URL}/firmware/demo/history/tag-new/demo.ota.bin")
        check("out-of-mirror-set entry was rewritten",
              by_version["v1.0.0"]["ota"]["path"]
              == f"{REPO_URL}/releases/download/tag-old/demo.ota.bin")
        check("missing-asset entry was rewritten despite no local file",
              by_version["v1.1.0"]["ota"]["path"]
              == f"{REPO_URL}/releases/download/tag-missing-asset/demo.ota.bin")

        dest = os.path.join(firmware_root, "demo", "history", "tag-new", "demo.ota.bin")
        check("binary not copied into the Pages tree", os.path.isfile(dest))
        if os.path.isfile(dest):
            with open(dest, "rb") as f:
                check("copied binary content mismatch", f.read() == b"firmware-bytes")

        # Idempotent: a second run over the same tree is a no-op (already
        # mirrored entries are detected by their Pages URL and skipped).
        mirrored_again, warnings_again = run(
            firmware_root, assets_dir,
            mirror_tags=["tag-new", "tag-missing-asset"],
            devices=["demo"])
        check("re-run reported a change on an already-mirrored slug",
              mirrored_again == [])
        check("re-run did not repeat the missing-asset warning",
              any("tag-missing-asset" in w for w in warnings_again))
        with open(os.path.join(firmware_root, "demo", "versions.json")) as f:
            check("re-run mutated an already-correct versions.json",
                  json.load(f) == written)

    if failures:
        for msg in failures:
            print(f"{PREFIX} self-test: {msg}", file=sys.stderr)
        return 1
    print(f"{PREFIX} self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir",
                        help="dir holding <tag>/<slug>.ota.bin release assets")
    parser.add_argument("--firmware-root",
                        help="firmware dir holding <slug>/versions.json to rewrite")
    parser.add_argument("--tags", nargs="*", default=[],
                        help="release tags eligible for mirroring")
    parser.add_argument(
        "--devices-json",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "devices.json"
        ),
        help="devices.json listing the slugs to check",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    missing = [
        n for n, v in (
            ("--assets-dir", args.assets_dir),
            ("--firmware-root", args.firmware_root),
        )
        if not v
    ]
    if missing:
        parser.error(f"missing required arguments: {', '.join(missing)}")

    with open(args.devices_json, encoding="utf-8") as f:
        devices = json.load(f)["devices"]

    run(args.firmware_root, args.assets_dir, args.tags, devices)


if __name__ == "__main__":
    main()
