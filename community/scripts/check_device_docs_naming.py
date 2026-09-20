#!/usr/bin/env python3
"""
check_device_docs_naming.py – Enforce that a device's own docs file is
named COMMUNITY.md, not README.md.

Why this exists
----------------
Every existing device folder documents itself in COMMUNITY.md. PR #171
(waveshare-esp32-p4-touch-lcd-7b) introduced a devices/<slug>/README.md
instead — nothing else in the pipeline checks the filename a contributor
picks for a device's own docs, so it went unnoticed until a manual review
caught the inconsistency. Left alone, README.md there also risks being
mistaken by tooling or a future contributor for the repo's own root
README.md when skimming a device folder.

Usage:
    python3 community/scripts/check_device_docs_naming.py
    python3 community/scripts/check_device_docs_naming.py --self-test
"""

import json
import os
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


def check_device(slug, repo_root=None):
    """Return a list of error strings for one device (empty = OK)."""
    root = repo_root or REPO_ROOT
    readme_path = os.path.join(root, "devices", slug, "README.md")
    if os.path.isfile(readme_path):
        return [
            f"{slug}: devices/{slug}/README.md should be COMMUNITY.md "
            f"instead — every other device documents itself there, and "
            f"README.md there is easily mistaken for the repo's own root "
            f"README.md. Rename it."
        ]
    return []


def check_all(repo_root=None):
    root = repo_root or REPO_ROOT
    with open(os.path.join(root, "community", "devices.json"),
              "r", encoding="utf-8") as f:
        slugs = json.load(f).get("devices", [])
    if not slugs:
        print("No community devices registered. Nothing to check.")
        return 0

    errors = []
    for slug in slugs:
        errors.extend(check_device(slug, root))

    if errors:
        print("[check_device_docs_naming] FAIL:")
        for msg in errors:
            print(f"  - {msg}")
        return 1
    print(f"[check_device_docs_naming] OK — {len(slugs)} device(s) use "
          f"COMMUNITY.md, not README.md")
    return 0


# =============================================================================
# Self-test
# =============================================================================


def self_test():
    import shutil
    import tempfile

    print("Running check_device_docs_naming self-test...")
    failures = []
    tmp = tempfile.mkdtemp(prefix="check_device_docs_naming_test_")
    try:
        def write_device(slug, filename):
            d = os.path.join(tmp, "devices", slug)
            os.makedirs(d, exist_ok=True)
            if filename:
                with open(os.path.join(d, filename), "w") as f:
                    f.write("docs\n")

        write_device("good-community", "COMMUNITY.md")
        write_device("bad-readme", "README.md")
        write_device("no-docs-file", None)

        os.makedirs(os.path.join(tmp, "community"), exist_ok=True)
        with open(os.path.join(tmp, "community", "devices.json"), "w") as f:
            json.dump({"devices": ["good-community", "bad-readme",
                                    "no-docs-file"]}, f)

        if check_device("good-community", tmp):
            failures.append("COMMUNITY.md flagged as error")
        else:
            print("  ✓ devices/<slug>/COMMUNITY.md passes")

        errs = check_device("bad-readme", tmp)
        if not errs:
            failures.append("devices/<slug>/README.md was not caught")
        else:
            print("  ✓ devices/<slug>/README.md is caught")

        if check_device("no-docs-file", tmp):
            failures.append("a device with neither file was flagged")
        else:
            print("  ✓ a device with no per-device docs file at all is "
                  "not flagged (not required)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        for msg in failures:
            print(f"[check_device_docs_naming] ERROR: self-test: {msg}",
                  file=sys.stderr)
        return 1
    print("\nAll check_device_docs_naming self-tests passed! ✓")
    return 0


def main():
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    sys.exit(check_all())


if __name__ == "__main__":
    main()
