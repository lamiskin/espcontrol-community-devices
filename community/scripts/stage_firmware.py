#!/usr/bin/env python3
"""
stage_firmware.py – Stage the Pages firmware tree (firmware/<slug>/manifest.json)
from a release's downloaded manifest assets.

The tree is driven by the REGISTRY, not by whatever assets the latest release
happens to carry. Releases are immutable, so a device removed from
community/devices.json keeps shipping its manifest asset in every older
release; an asset-driven staging loop therefore kept publishing an update feed
for a device that no longer exists here (that is how firmware/lilygo-jc3248w535/
survived its removal in e7546b2).

Two registries decide what gets published:

  community/devices.json         – live devices. Each slug is staged from its
                                   own <slug>-manifest.json release asset.

  community/retired-devices.json – devices removed from the project that still
                                   have panels in the field. Panels poll
                                   firmware/<slug>/manifest.json forever, so
                                   dropping the path silently ends their
                                   updates. Instead each retired slug is staged
                                   with a HANDOVER manifest built from its
                                   successor's release manifest: the panel's
                                   next update check offers the successor's
                                   build, installs it, and from then on polls
                                   the successor's feed. This is the mechanic
                                   docs/reference/graduation.md defines for
                                   upstream graduation, reused for in-project
                                   removals.

                                   Schema, keyed by the retired slug:
                                     successor     – slug in devices.json whose
                                                     build the panels move to
                                     removed       – YYYY-MM-DD, when it left
                                     publish_until – YYYY-MM-DD, when the feed
                                                     retires (>= 12 months after
                                                     removal, per graduation.md)
                                     reason        – why, for whoever curls it

Anything else found in release-assets/ is ignored with a warning: it is an
older release's leftover, not something this site should publish.

Usage:
    python3 community/scripts/stage_firmware.py \
        --assets release-assets --dest community-pages/firmware --tag <tag>
    python3 community/scripts/stage_firmware.py --self-test
"""

import argparse
import datetime
import json
import os
import shutil
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

PREFIX = "[stage_firmware]"


def error(msg):
    print(f"{PREFIX} ERROR: {msg}", file=sys.stderr)


def warn(msg):
    print(f"{PREFIX} WARNING: {msg}", file=sys.stderr)


def load_registered(repo_root=None):
    """Live device slugs, in registry order."""
    root = repo_root or REPO_ROOT
    path = os.path.join(root, "community", "devices.json")
    with open(path, encoding="utf-8") as f:
        return list(json.load(f).get("devices", []))


def load_retired(repo_root=None):
    """
    Retired slug -> handover entry. The file is optional: a project with no
    retired devices simply has none.
    """
    root = repo_root or REPO_ROOT
    path = os.path.join(root, "community", "retired-devices.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return dict(json.load(f).get("retired", {}))


def available_slugs(assets_dir):
    """
    Slugs with a <slug>-manifest.json in the downloaded release assets.

    Excludes *-recovery-manifest.json (issue #98, staged separately by
    stage_recovery_manifests.py): it ends in "-manifest.json" too, so
    without this it would be misread as the regular manifest for a
    nonexistent "<slug>-recovery" device and warn on every release.
    """
    if not os.path.isdir(assets_dir):
        return set()
    return {
        name[: -len("-manifest.json")]
        for name in os.listdir(assets_dir)
        if name.endswith("-manifest.json")
        and not name.endswith("-recovery-manifest.json")
    }


def _parse_date(value):
    return datetime.date.fromisoformat(value)


def plan(registered, retired, available, today):
    """
    Decide what to stage. Returns (actions, warnings, errors).

    Each action is a dict:
        slug     – the firmware/<slug>/ path to publish
        source   – the slug whose release manifest supplies the content
        handover – the retirement entry when slug != source, else None
    """
    actions, warnings, errors = [], [], []

    for slug in registered:
        if slug in available:
            actions.append({"slug": slug, "source": slug, "handover": None})
        else:
            # A device added since the last release has no binaries yet. The
            # docs/installer deploy must still go out, so this is not fatal.
            warnings.append(
                f"'{slug}' is registered but this release has no "
                f"{slug}-manifest.json — its feed will not be published until "
                f"the next release builds it")

    for slug, entry in sorted(retired.items()):
        if slug in registered:
            errors.append(
                f"'{slug}' is in both devices.json and retired-devices.json — "
                f"a device is either live or retired, not both")
            continue

        successor = entry.get("successor")
        if not successor:
            errors.append(
                f"retired '{slug}' has no successor — every retired device "
                f"needs a handover target (see graduation.md)")
            continue
        if successor not in registered:
            errors.append(
                f"retired '{slug}' hands over to '{successor}', which is not "
                f"in devices.json — panels would be sent to a device this "
                f"project no longer builds")
            continue

        try:
            publish_until = _parse_date(entry.get("publish_until", ""))
        except ValueError:
            errors.append(
                f"retired '{slug}' has an invalid publish_until "
                f"{entry.get('publish_until')!r} — expected YYYY-MM-DD")
            continue

        if today > publish_until:
            print(f"{PREFIX} retired '{slug}': handover window closed "
                  f"{publish_until} — feed no longer published")
            continue

        if successor not in available:
            # Fatal: silently skipping drops the feed the handover exists to
            # keep alive, and the release job hard-fails unless every
            # registered device built, so this means something is wrong.
            errors.append(
                f"retired '{slug}' needs {successor}-manifest.json to build "
                f"its handover manifest, but this release has no such asset")
            continue

        actions.append(
            {"slug": slug, "source": successor, "handover": entry})

    known = set(registered) | set(retired)
    for slug in sorted(available - known):
        warnings.append(
            f"release asset '{slug}-manifest.json' matches no device in "
            f"devices.json or retired-devices.json — not published")

    return actions, warnings, errors


def build_handover_manifest(successor_manifest, slug, entry):
    """
    The successor's manifest, republished at the retired slug's path. Content
    is the successor's verbatim (same version, same binaries, same md5) so the
    panel installs the successor's build; the `handover` block only documents
    the redirect for anyone reading the feed.
    """
    manifest = dict(successor_manifest)
    manifest["handover"] = {
        "from": slug,
        "to": entry.get("successor"),
        "reason": entry.get("reason", ""),
        "published_until": entry.get("publish_until", ""),
    }
    return manifest


def stage(actions, assets_dir, dest_dir):
    """Write the planned manifests into dest_dir/<slug>/manifest.json."""
    for action in actions:
        slug, source = action["slug"], action["source"]
        src = os.path.join(assets_dir, f"{source}-manifest.json")
        out_dir = os.path.join(dest_dir, slug)
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, "manifest.json")

        if action["handover"] is None:
            shutil.copyfile(src, out)
            print(f"{PREFIX} staged {slug}/manifest.json")
            continue

        with open(src, encoding="utf-8") as f:
            successor_manifest = json.load(f)
        manifest = build_handover_manifest(
            successor_manifest, slug, action["handover"])
        with open(out, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
        print(f"{PREFIX} staged {slug}/manifest.json "
              f"(handover -> {source} {manifest.get('version', '?')})")


def run(assets_dir, dest_dir, tag=None, repo_root=None, today=None):
    registered = load_registered(repo_root)
    retired = load_retired(repo_root)
    available = available_slugs(assets_dir)
    today = today or datetime.date.today()

    if not available:
        # Same posture as the workflow's "no release exists yet" path: publish
        # the docs site without a firmware tree rather than fail the deploy.
        # A release that dropped only *some* manifests is a different story and
        # is caught below.
        warn(f"no *-manifest.json assets in {assets_dir} — deploying without "
             f"a firmware tree")
        return 0

    actions, warnings, errors = plan(registered, retired, available, today)

    for msg in warnings:
        warn(msg)
    if errors:
        for msg in errors:
            error(msg)
        return 1

    if tag:
        print(f"{PREFIX} staging firmware manifests from {tag}")
    stage(actions, assets_dir, dest_dir)
    print(f"{PREFIX} {len(actions)} manifest(s) staged into {dest_dir}")
    return 0


def self_test():
    import tempfile

    failures = []
    today = datetime.date(2026, 7, 25)

    def check(name, cond):
        if not cond:
            failures.append(name)

    registered = ["alpha", "beta"]
    retired = {
        "old-alpha": {
            "successor": "alpha",
            "removed": "2026-07-22",
            "publish_until": "2027-07-22",
            "reason": "duplicate",
        }
    }

    # A *-recovery-manifest.json asset (issue #98) must never be misread as
    # the regular manifest for a nonexistent "<slug>-recovery" device.
    with tempfile.TemporaryDirectory(prefix="stage_firmware_recovery_test_") as recovery_tmp:
        for name in ("alpha-manifest.json", "alpha-recovery-manifest.json"):
            with open(os.path.join(recovery_tmp, name), "w") as f:
                f.write("{}")
        found = available_slugs(recovery_tmp)
        check("recovery manifest misread as its own device",
              found == {"alpha"})

    # Live devices staged from their own asset; handover staged from the
    # successor's; a stale asset for a slug in neither registry is dropped.
    actions, warnings, errors = plan(
        registered, retired, {"alpha", "beta", "old-alpha", "ghost"}, today)
    check("unexpected errors on the happy path", not errors)
    staged = {a["slug"]: a["source"] for a in actions}
    check("live devices not staged from themselves",
          staged.get("alpha") == "alpha" and staged.get("beta") == "beta")
    check("handover not staged from its successor",
          staged.get("old-alpha") == "alpha")
    check("stale 'ghost' asset was staged", "ghost" not in staged)
    check("no warning for the ignored 'ghost' asset",
          any("ghost" in w for w in warnings))

    # The retired slug's own leftover asset must never win over the handover:
    # that is the exact regression this script exists to prevent.
    for action in actions:
        if action["slug"] == "old-alpha":
            check("retired slug staged from its own stale asset",
                  action["source"] == "alpha" and action["handover"])

    # A registered device with no asset yet (added since the last release)
    # warns but must not block the deploy.
    actions, warnings, errors = plan(
        registered, {}, {"alpha"}, today)
    check("missing asset for a registered device was fatal", not errors)
    check("missing asset for a registered device did not warn",
          any("beta" in w for w in warnings))
    check("device without an asset was staged",
          all(a["slug"] != "beta" for a in actions))

    # Past publish_until the feed retires for real.
    expired = {"old-alpha": dict(retired["old-alpha"],
                                 publish_until="2026-07-24")}
    actions, _, errors = plan(registered, expired, {"alpha", "old-alpha"},
                              today)
    check("expired handover errored", not errors)
    check("expired handover still staged",
          all(a["slug"] != "old-alpha" for a in actions))
    # ...and on the last day it is still published.
    same_day = {"old-alpha": dict(retired["old-alpha"],
                                  publish_until="2026-07-25")}
    actions, _, _ = plan(registered, same_day, {"alpha", "old-alpha"}, today)
    check("handover retired a day early",
          any(a["slug"] == "old-alpha" for a in actions))

    # Misconfigurations are fatal, not silently skipped.
    _, _, errors = plan(registered, retired, {"beta", "old-alpha"}, today)
    check("missing successor asset was not fatal",
          any("old-alpha" in e for e in errors))

    _, _, errors = plan(
        registered, {"old-alpha": dict(retired["old-alpha"],
                                       successor="gone")},
        {"alpha", "beta"}, today)
    check("unregistered successor was not fatal", errors)

    _, _, errors = plan(
        registered, {"old-alpha": {"removed": "2026-07-22",
                                   "publish_until": "2027-07-22"}},
        {"alpha", "beta"}, today)
    check("successor-less retirement was not fatal", errors)

    _, _, errors = plan(
        registered, {"old-alpha": dict(retired["old-alpha"],
                                       publish_until="soon")},
        {"alpha", "beta"}, today)
    check("invalid publish_until was not fatal", errors)

    _, _, errors = plan(
        ["alpha", "beta", "old-alpha"], retired, {"alpha", "beta", "old-alpha"},
        today)
    check("slug in both registries was not fatal", errors)

    # Handover content is the successor's build, with the redirect documented.
    successor_manifest = {
        "name": "Alpha Panel",
        "version": "v1.2.3",
        "builds": [{"chipFamily": "ESP32-S3",
                    "ota": {"path": "https://x/alpha.ota.bin", "md5": "abc"}}],
    }
    handover = build_handover_manifest(
        successor_manifest, "old-alpha", retired["old-alpha"])
    check("handover manifest lost the successor's version",
          handover["version"] == "v1.2.3")
    check("handover manifest does not point at the successor's binary",
          handover["builds"][0]["ota"]["path"] == "https://x/alpha.ota.bin")
    check("handover manifest is not self-describing",
          handover["handover"]["from"] == "old-alpha"
          and handover["handover"]["to"] == "alpha")
    check("build_handover_manifest mutated its input",
          "handover" not in successor_manifest)

    # End to end on a temp tree, including the real registries on disk.
    with tempfile.TemporaryDirectory(prefix="stage_firmware_test_") as tmp:
        root = os.path.join(tmp, "repo")
        os.makedirs(os.path.join(root, "community"))
        with open(os.path.join(root, "community", "devices.json"), "w") as f:
            json.dump({"devices": registered}, f)
        with open(os.path.join(root, "community",
                               "retired-devices.json"), "w") as f:
            json.dump({"retired": retired}, f)

        assets = os.path.join(tmp, "assets")
        os.makedirs(assets)
        for slug in ("alpha", "beta", "old-alpha", "ghost"):
            with open(os.path.join(assets, f"{slug}-manifest.json"), "w") as f:
                json.dump(dict(successor_manifest, name=slug), f)

        dest = os.path.join(tmp, "firmware")
        rc = run(assets, dest, tag="t", repo_root=root, today=today)
        check("run() failed on a valid tree", rc == 0)
        check("ghost feed was published",
              not os.path.exists(os.path.join(dest, "ghost")))
        with open(os.path.join(dest, "old-alpha", "manifest.json")) as f:
            written = json.load(f)
        check("staged handover is not the successor's manifest",
              written["name"] == "alpha" and "handover" in written)
        with open(os.path.join(dest, "beta", "manifest.json")) as f:
            check("live device manifest was rewritten",
                  json.load(f)["name"] == "beta")

        # An empty asset dir (no release, or a release carrying no manifests)
        # deploys a firmware-less site rather than failing, matching the
        # workflow's own "no releases exist yet" path.
        dest2 = os.path.join(tmp, "firmware2")
        rc = run(os.path.join(tmp, "nonexistent"), dest2,
                 repo_root=root, today=today)
        check("missing asset dir was fatal", rc == 0)
        check("empty asset dir still wrote a firmware tree",
              not os.path.exists(dest2))

    # The repo's own registries must be internally consistent.
    real_registered = load_registered()
    real_retired = load_retired()
    _, _, errors = plan(real_registered, real_retired,
                        set(real_registered) | set(real_retired), today)
    for msg in errors:
        failures.append(f"repo registries: {msg}")

    if failures:
        for msg in failures:
            error(f"self-test: {msg}")
        return 1
    print(f"{PREFIX} self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", default="release-assets",
                        help="directory holding downloaded *-manifest.json "
                             "release assets")
    parser.add_argument("--dest", default="community-pages/firmware",
                        help="firmware tree to stage into")
    parser.add_argument("--tag", help="release tag, for logging")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    sys.exit(run(args.assets, args.dest, args.tag))


if __name__ == "__main__":
    main()
