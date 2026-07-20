#!/usr/bin/env python3
"""
postprocess_www.py – Community post-processing of the built web GUI bundle
(www.js) before it is published to Pages.

Two jobs, both designed to survive upstream refactors:

1. URL rewrites — the panel's web GUI is upstream's bundle verbatim, so a
   handful of links point at upstream's repo/docs. The user-facing entry
   points are rewritten to community equivalents; deep functional-docs
   links and the upstream author's support button are deliberately kept.
   Every rewrite is an EXACT quoted-string replacement with a required
   match count — if upstream renames or removes a URL at a pin bump, this
   script FAILS LOUDLY instead of silently shipping wrong links.

2. Banner injection — a self-contained IIFE appended to the bundle that
   prepends an "unofficial community build" banner to the page. It touches
   no upstream code paths (pure append), so it is immune to upstream
   refactors by construction.

Usage:
    python3 community/scripts/postprocess_www.py <path-to-www.js>
    python3 community/scripts/postprocess_www.py --self-test
"""

import argparse
import sys

MARKER = "/*espcontrol-community-postprocess:v1*/"

COMMUNITY_DOCS = "https://lamiskin.github.io/espcontrol-community-devices/"
COMMUNITY_ISSUES = (
    "https://github.com/lamiskin/espcontrol-community-devices/issues")

# Exact quoted strings so shared prefixes (e.g. the media-card deep link)
# can never be caught by a rewrite. (old, new, exact_expected_count)
REWRITES = [
    # Settings "Docs" tab — the GUI's main documentation entry point.
    ('"https://jtenniswood.github.io/espcontrol/"',
     f'"{COMMUNITY_DOCS}"', 1),
    # Firmware/release-notes link builder — our site mirrors the layout.
    ('"https://jtenniswood.github.io/espcontrol/firmware/"',
     f'"{COMMUNITY_DOCS}firmware/"', 1),
]

# Strings that must remain UNTOUCHED after rewriting — deliberate keeps.
MUST_REMAIN = [
    # Deep functional-docs link: functional documentation lives upstream.
    "https://jtenniswood.github.io/espcontrol/card-types/media/",
    # The upstream author's support button stays his.
    "https://www.buymeacoffee.com/jtenniswood",
]

BANNER_JS = (
    "\n" + MARKER + "\n"
    "(function(){\n"
    "  function addBanner(){\n"
    "    if (document.getElementById('community-banner')) return;\n"
    "    try { if (sessionStorage.getItem('community-banner-dismissed')) return; } catch (e) {}\n"
    "    var b = document.createElement('div');\n"
    "    b.id = 'community-banner';\n"
    "    b.style.cssText = 'box-sizing:border-box;width:100%;padding:8px 36px 8px 12px;"
    "background:#78350f;color:#fef3c7;font:13px/1.45 -apple-system,system-ui,sans-serif;"
    "position:relative;text-align:center;';\n"
    "    b.innerHTML = '\\u26a0\\ufe0e Unofficial <strong>community</strong> EspControl build. "
    "Report issues only to the <a href=\"" + COMMUNITY_ISSUES + "\" target=\"_blank\" rel=\"noopener\" "
    "style=\"color:#fde68a;text-decoration:underline;\">community repo</a> \\u2014 never upstream. "
    "Community devices may be buggier than officially supported panels.';\n"
    "    var x = document.createElement('button');\n"
    "    x.textContent = '\\u00d7';\n"
    "    x.setAttribute('aria-label', 'Dismiss');\n"
    "    x.style.cssText = 'position:absolute;right:8px;top:4px;background:none;border:none;"
    "color:#fde68a;font-size:18px;cursor:pointer;padding:2px 6px;';\n"
    "    x.onclick = function(){\n"
    "      b.remove();\n"
    "      try { sessionStorage.setItem('community-banner-dismissed', '1'); } catch (e) {}\n"
    "    };\n"
    "    b.appendChild(x);\n"
    "    document.body.insertBefore(b, document.body.firstChild);\n"
    "  }\n"
    "  if (document.readyState === 'loading') {\n"
    "    document.addEventListener('DOMContentLoaded', addBanner);\n"
    "  } else {\n"
    "    addBanner();\n"
    "  }\n"
    "})();\n"
)


def postprocess(content):
    """Return (new_content, messages). Raises ValueError on drift."""
    if MARKER in content:
        return content, ["already post-processed — no changes"]

    messages = []
    for old, new, expected in REWRITES:
        count = content.count(old)
        if count != expected:
            raise ValueError(
                f"expected exactly {expected} occurrence(s) of {old} in "
                f"www.js but found {count} — upstream's web GUI links "
                f"changed at this pin; update REWRITES in "
                f"postprocess_www.py")
        content = content.replace(old, new)
        messages.append(f"rewrote {count}x {old} -> {new}")

    for keep in MUST_REMAIN:
        if keep not in content:
            raise ValueError(
                f"deliberate-keep string missing after rewrite: {keep} — "
                f"a rewrite was too broad or upstream changed; fix "
                f"postprocess_www.py")

    content += BANNER_JS
    messages.append("appended community banner")
    return content, messages


def self_test():
    fixture = (
        'var docsTab="https://jtenniswood.github.io/espcontrol/";'
        'var fw="https://jtenniswood.github.io/espcontrol/firmware/";'
        'var deep="https://jtenniswood.github.io/espcontrol/card-types/media/#media-content";'
        'var coffee="https://www.buymeacoffee.com/jtenniswood";'
    )
    failures = []

    out, _ = postprocess(fixture)
    if '"https://jtenniswood.github.io/espcontrol/"' in out:
        failures.append("docs tab not rewritten")
    if f'"{COMMUNITY_DOCS}"' not in out:
        failures.append("community docs URL missing")
    if f'"{COMMUNITY_DOCS}firmware/"' not in out:
        failures.append("community firmware URL missing")
    if "card-types/media/#media-content" not in out:
        failures.append("deep functional link was damaged")
    if "buymeacoffee.com/jtenniswood" not in out:
        failures.append("support button was damaged")
    if MARKER not in out or "community-banner" not in out:
        failures.append("banner not appended")

    out2, msgs = postprocess(out)
    if out2 != out or "already post-processed" not in msgs[0]:
        failures.append("not idempotent")

    try:
        postprocess(fixture.replace(
            'https://jtenniswood.github.io/espcontrol/firmware/', 'x'))
        failures.append("missing-URL drift did not raise")
    except ValueError:
        pass

    try:
        postprocess(fixture + fixture)  # counts doubled
        failures.append("count drift did not raise")
    except ValueError:
        pass

    if failures:
        for msg in failures:
            print(f"[postprocess_www] self-test FAIL: {msg}",
                  file=sys.stderr)
        return 1
    print("[postprocess_www] self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())
    if not args.path:
        parser.error("path to www.js required (or --self-test)")

    with open(args.path, encoding="utf-8") as f:
        content = f.read()
    try:
        content, messages = postprocess(content)
    except ValueError as exc:
        print(f"[postprocess_www] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    with open(args.path, "w", encoding="utf-8") as f:
        f.write(content)
    for msg in messages:
        print(f"[postprocess_www] {msg}")


if __name__ == "__main__":
    main()
