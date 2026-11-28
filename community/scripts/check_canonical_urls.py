#!/usr/bin/env python3
"""
check_canonical_urls.py – Reject contributor-fork URLs for this repository.

Every user-facing ESPHome entry file, package manifest, web/OTA override and
build profile must resolve this project from its canonical home:

    GitHub  lamiskin/espcontrol-community-devices
    Pages   lamiskin.github.io/espcontrol-community-devices

A fork URL still works for the contributor who wrote it, but silently pins
everyone who copies the snippet or installs the firmware to a copy that stops
receiving updates. This is not hypothetical: the 7B port shipped its
esphome.yaml pointing at a personal fork, leaving the browser installer on the
canonical release while manual installs stayed on a months-old pin.

The check reads every non-binary file in the tree (anything that decodes as
UTF-8), skipping generated build trees and test fixtures, so a fork reference
cannot reappear in a device config, build profile, status table or docs page.
There is no suffix allowlist: a new text format is covered without changing
this script.

Usage:
    python3 community/scripts/check_canonical_urls.py
    python3 community/scripts/check_canonical_urls.py --self-test
"""

import os
import re
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

CANONICAL_OWNER = "lamiskin"
REPO_NAME = "espcontrol-community-devices"

# Match the GitHub repository, GitHub Pages site and raw-content host for this
# project under any owner. The lookahead deliberately rejects look-alike names
# such as espcontrol-community-devices_CP10.1 or ...-fork, which are separate
# projects and not accidental copies of this one.
_TRAILING = r"(?:\.git)?(?![A-Za-z0-9_.-])"
_OWNER = r"(?P<owner>[A-Za-z0-9_.-]+)"

URL_CHECKS = (
    (
        "GitHub",
        re.compile(
            r"(?:https?://(?:www\.)?github\.com/"
            r"|(?:git\+)?ssh://(?:[^@/\s]+@)?github\.com(?::\d+)?/"
            r"|git@github\.com:"
            r"|github://)"
            + _OWNER
            + "/"
            + re.escape(REPO_NAME)
            + _TRAILING,
            re.IGNORECASE,
        ),
    ),
    (
        "Pages",
        re.compile(
            r"https?://"
            + _OWNER
            + r"\.github\.io/"
            + re.escape(REPO_NAME)
            + r"(?![A-Za-z0-9_.-])",
            re.IGNORECASE,
        ),
    ),
    (
        "raw.githubusercontent.com",
        re.compile(
            r"https?://raw\.githubusercontent\.com/"
            + _OWNER
            + "/"
            + re.escape(REPO_NAME)
            + r"(?![A-Za-z0-9_.-])",
            re.IGNORECASE,
        ),
    ),
)

# Media, fonts, archives and compiled objects are binary. Everything else is
# read as UTF-8 and skipped when it does not decode, so new text formats
# (.mts, LICENSE, Makefile, ...) are covered without an allowlist entry.
BINARY_SUFFIXES = {
    ".7z",
    ".avi",
    ".bin",
    ".bmp",
    ".bz2",
    ".eot",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".o",
    ".ogg",
    ".otf",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".tgz",
    ".tif",
    ".tiff",
    ".ttf",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xz",
    ".zip",
}
SKIP_DIRS = {
    ".git",
    ".assembly",
    ".esphome",
    ".venv",
    "__pycache__",
    "build",
    "community-pages",
    "dist",
    "node_modules",
    "release-assets",
    "site",
    "tests",
    "venv",
}


def iter_text_files(root):
    """Yield text files under root, skipping build trees and binaries."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            # Test fixtures deliberately use synthetic owners; they are not
            # part of the shipped config or docs.
            if name.startswith("test_"):
                continue
            if os.path.splitext(name)[1].lower() in BINARY_SUFFIXES:
                continue
            path = os.path.join(dirpath, name)
            if os.path.isfile(path):
                yield path


def scan_text(text, path):
    """Return a list of violations found in one file's text."""
    violations = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for kind, regex in URL_CHECKS:
            for match in regex.finditer(line):
                owner = match.group("owner")
                if owner.lower() == CANONICAL_OWNER:
                    continue
                violations.append(
                    {
                        "path": path,
                        "line": line_number,
                        "kind": kind,
                        "owner": owner,
                        "url": match.group(0),
                    }
                )
    return violations


def check_tree(root=None):
    """Return every violation under root (defaults to this repository)."""
    root = root or REPO_ROOT
    violations = []
    for path in iter_text_files(root):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            # A non-UTF-8 file cannot be a YAML/Markdown/JSON source we ship.
            continue
        violations.extend(scan_text(text, path))
    return violations


def _display_path(path, root):
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def check_all(root=None):
    root = root or REPO_ROOT
    violations = check_tree(root)
    if not violations:
        print(
            "[check_canonical_urls] OK — all repository URLs point at "
            f"{CANONICAL_OWNER}/{REPO_NAME} and "
            f"{CANONICAL_OWNER}.github.io/{REPO_NAME}"
        )
        return 0

    print("[check_canonical_urls] FAIL:")
    for violation in violations:
        print(
            f"  - {_display_path(violation['path'], root)}:"
            f"{violation['line']}: {violation['kind']} URL points at "
            f"'{violation['owner']}': {violation['url']}"
        )
    print(
        "  Every user-facing config must use "
        f"https://github.com/{CANONICAL_OWNER}/{REPO_NAME}/ or "
        f"https://{CANONICAL_OWNER}.github.io/{REPO_NAME}/. A fork URL "
        "silently pins users to a copy that stops receiving updates."
    )
    return 1


def self_test():
    import contextlib
    import io
    import shutil
    import tempfile

    failures = []
    tmp = tempfile.mkdtemp(prefix="check_canonical_urls_test_")
    try:

        def write(relative_path, text):
            path = os.path.join(tmp, relative_path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)

        write(
            "devices/ok/esphome.yaml",
            "packages:\n"
            "  setup:\n"
            "    url: https://github.com/lamiskin/"
            "espcontrol-community-devices/\n",
        )
        write(
            "devices/ok/packages.yaml",
            "web_server:\n"
            "  js_url: https://lamiskin.github.io/"
            "espcontrol-community-devices/webserver/www.js\n"
            "update:\n"
            "  - id: !extend firmware_update\n"
            "    source: https://lamiskin.github.io/"
            "espcontrol-community-devices/firmware/example/manifest.json\n",
        )
        write(
            "builds/ok.factory.yaml",
            "dashboard_import:\n"
            "  package_import_url: github://lamiskin/"
            "espcontrol-community-devices/devices/ok/esphome.yaml@main\n",
        )
        write(
            "community/STATUS.md",
            "| Device | Source |\n"
            "|---|---|\n"
            "| OK | [PR #1](https://github.com/lamiskin/"
            "espcontrol-community-devices/pull/1) |\n",
        )
        write(
            "docs/.vitepress/config.mts",
            "const site = 'https://lamiskin.github.io/"
            "espcontrol-community-devices/'\n"
            "const clone = 'ssh://git@github.com/lamiskin/"
            "espcontrol-community-devices.git'\n",
        )
        # A different project with a similar name must not be mistaken for a
        # fork of this repository.
        write(
            "docs/lookalike.md",
            "https://github.com/example/"
            "espcontrol-community-devices_CP10.1\n"
            "https://github.com/example/"
            "espcontrol-community-devices-fork\n",
        )

        if check_tree(tmp):
            failures.append(
                "canonical URLs or a look-alike project were flagged: "
                f"{check_tree(tmp)}"
            )

        # Build the fake owner at runtime so this test fixture does not
        # itself trip the repository scan.
        fork_owner = "some" + "fork"
        write(
            "devices/bad/esphome.yaml",
            "packages:\n"
            "  setup:\n"
            f"    url: https://github.com/{fork_owner}/"
            "espcontrol-community-devices/\n",
        )
        write(
            "devices/bad/packages.yaml",
            "web_server:\n"
            f"  js_url: https://{fork_owner}.github.io/"
            "espcontrol-community-devices/webserver/www.js\n",
        )
        write(
            "builds/bad.factory.yaml",
            "dashboard_import:\n"
            f"  package_import_url: github://{fork_owner}/"
            "espcontrol-community-devices/devices/bad/esphome.yaml@main\n",
        )
        write(
            "docs/bad.md",
            f"https://raw.githubusercontent.com/{fork_owner}/"
            "espcontrol-community-devices/main/devices/bad/esphome.yaml\n"
            f"git@github.com:{fork_owner}/"
            "espcontrol-community-devices.git\n"
            f"ssh://git@github.com/{fork_owner}/"
            "espcontrol-community-devices.git\n",
        )
        # .mts and extensionless text files must not escape the scan.
        write(
            "docs/bad.mts",
            f"const site = 'https://{fork_owner}.github.io/"
            "espcontrol-community-devices/'\n",
        )
        write(
            "NOTICE",
            f"https://github.com/{fork_owner}/"
            "espcontrol-community-devices\n",
        )

        violations = check_tree(tmp)
        if len(violations) != 8:
            failures.append(
                f"expected 8 fork violations, got {len(violations)}: "
                f"{violations}"
            )
        with contextlib.redirect_stdout(io.StringIO()):
            aggregate_status = check_all(tmp)
        if aggregate_status == 0:
            failures.append("check_all passed despite fork URLs")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        for message in failures:
            print(
                f"[check_canonical_urls] ERROR: self-test: {message}",
                file=sys.stderr,
            )
        return 1
    print("[check_canonical_urls] self-test passed")
    return 0


def main():
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    sys.exit(check_all())


if __name__ == "__main__":
    main()
