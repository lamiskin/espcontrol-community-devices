#!/usr/bin/env python3
"""
label_issue.py – Given a bug-report issue body, print the device label to
apply (or nothing). Used by community-issue-labeler.yml.

GitHub issue forms render a dropdown answer as a "### <label>" heading
followed by the selected value. This reads the "Which device?" answer and
maps the device name back to its device:<slug> label via
community/device-labels.json.

Usage:
    BODY=... python3 community/scripts/label_issue.py     # body from $BODY
    python3 community/scripts/label_issue.py --self-test
"""

import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
HEADING = "Which device?"


def load_name_to_label(repo_root=None):
    root = repo_root or REPO_ROOT
    with open(os.path.join(root, "community",
                           "device-labels.json")) as f:
        data = json.load(f)
    return {d["name"]: d["label"] for d in data["devices"]}


def selected_device(body):
    """Return the value under the 'Which device?' heading, or None."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if re.match(r'^#{1,6}\s+' + re.escape(HEADING) + r'\s*$',
                    line.strip()):
            for value in lines[i + 1:]:
                if value.strip():
                    return value.strip()
            return None
    return None


def label_for(body, name_to_label):
    name = selected_device(body)
    if name is None:
        return None
    return name_to_label.get(name)  # None for "Other / not sure"


def self_test():
    failures = []
    name_to_label = {
        "Device A": "device:dev-a",
        "Device B": "device:dev-b",
    }

    body_a = ("### Which device?\n\nDevice A\n\n"
              "### What happened?\n\nIt broke\n")
    if label_for(body_a, name_to_label) != "device:dev-a":
        failures.append("did not resolve Device A")

    body_other = "### Which device?\n\nOther / not sure\n"
    if label_for(body_other, name_to_label) is not None:
        failures.append("escape-hatch should map to no label")

    body_none = "### What happened?\n\nno dropdown here\n"
    if label_for(body_none, name_to_label) is not None:
        failures.append("missing dropdown should yield no label")

    # heading with trailing spaces / different level
    body_h2 = "## Which device?  \n\nDevice B\n"
    if label_for(body_h2, name_to_label) != "device:dev-b":
        failures.append("heading variant not handled")

    if failures:
        for m in failures:
            print(f"[label_issue] self-test FAIL: {m}", file=sys.stderr)
        return 1
    print("[label_issue] self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(self_test())

    body = os.environ.get("BODY", "")
    label = label_for(body, load_name_to_label())
    if label:
        print(label)


if __name__ == "__main__":
    main()
