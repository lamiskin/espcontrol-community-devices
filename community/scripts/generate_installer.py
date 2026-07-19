#!/usr/bin/env python3
"""Generate the ESP Web Tools installer page at community-pages/index.html."""

import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    # Read devices
    devices_path = os.path.join(REPO_ROOT, "community", "devices.json")
    with open(devices_path) as f:
        devices = json.load(f)["devices"]

    # Read STATUS.md to determine device statuses
    status_path = os.path.join(REPO_ROOT, "community", "STATUS.md")
    statuses = {}
    if os.path.isfile(status_path):
        with open(status_path) as f:
            for line in f:
                # Parse: | Name | slug | Status | ... |
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 5:
                    slug = parts[2]
                    status = parts[3]
                    name = parts[1]
                    if slug in devices:
                        statuses[slug] = {"name": name, "status": status}

    # Read catalog fragment for device names
    catalog_path = os.path.join(REPO_ROOT, "community", "catalog-fragment.json")
    catalog = {}
    if os.path.isfile(catalog_path):
        with open(catalog_path) as f:
            catalog = json.load(f).get("devices", {})

    # Generate HTML
    device_buttons = []
    for slug in sorted(devices):
        info = statuses.get(slug, {})
        status = info.get("status", "Untested")

        # Skip Broken devices (only Working and Untested are listed)
        if status == "Broken":
            continue

        name = info.get("name", "")
        if not name and slug in catalog:
            name = catalog[slug].get("config", {}).get("public", {}).get("name", slug)
        if not name:
            name = slug

        badge = ""
        if status == "Untested":
            badge = ' <span class="badge untested">not yet hardware-verified</span>'

        device_buttons.append(f"""    <div class="device">
      <h3>{name}{badge}</h3>
      <esp-web-install-button manifest="firmware/{slug}/manifest.json">
        <button slot="activate">Install</button>
      </esp-web-install-button>
    </div>""")

    buttons_html = "\n".join(device_buttons)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EspControl Community Devices - Installer</title>
  <script type="module" src="https://unpkg.com/esp-web-tools@10/dist/web/install-button.js?module"></script>
  <style>
    body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 2rem; }}
    .banner {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 1rem; margin-bottom: 2rem; }}
    .banner strong {{ color: #856404; }}
    .device {{ border: 1px solid #ddd; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; }}
    .device h3 {{ margin: 0; }}
    .badge {{ font-size: 0.75rem; padding: 0.2rem 0.5rem; border-radius: 4px; vertical-align: middle; }}
    .badge.untested {{ background: #e2e3e5; color: #383d41; }}
    a {{ color: #0366d6; }}
    footer {{ margin-top: 3rem; font-size: 0.875rem; color: #666; }}
  </style>
</head>
<body>
  <h1>EspControl Community Devices</h1>

  <div class="banner">
    <strong>Unofficial.</strong> This installer is not maintained by or affiliated with the
    <a href="https://github.com/jtenniswood/espcontrol">upstream EspControl project</a>.
  </div>

  <p>Connect your device via USB and click Install to flash community firmware.</p>

{buttons_html}

  <footer>
    <p>
      Source: <a href="https://github.com/lamiskin/espcontrol-community-devices">lamiskin/espcontrol-community-devices</a> |
      Status: <a href="https://github.com/lamiskin/espcontrol-community-devices/blob/main/community/STATUS.md">STATUS.md</a> |
      Upstream: <a href="https://github.com/jtenniswood/espcontrol">jtenniswood/espcontrol</a>
    </p>
  </footer>
</body>
</html>
"""

    # Write to community-pages/index.html
    output_dir = os.path.join(REPO_ROOT, "community-pages")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "index.html")
    with open(output_path, "w") as f:
        f.write(html)

    print(f"Generated installer page: {output_path}")
    print(f"  {len(device_buttons)} device(s) listed")


if __name__ == "__main__":
    main()
