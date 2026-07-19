#!/usr/bin/env python3
"""
convert_packages.py – Transform upstream-style packages.yaml (with relative
!include ../../common/... paths) into the remote-include form used by the
community devices repo.

Usage:
    python3 community/scripts/convert_packages.py devices/<slug>/packages.yaml
    python3 community/scripts/convert_packages.py --self-test
"""

import re
import sys
import os

UPSTREAM_URL = "https://github.com/jtenniswood/espcontrol"
PAGES_URL = "https://lamiskin.github.io/espcontrol-community-devices"

COMMUNITY_OVERRIDES = f"""\
# --- community hosting overrides ---
web_server:
  js_url: {PAGES_URL}/webserver/www.js?device=${{device_slug}}&v=${{firmware_version}}

update:
  - id: !extend firmware_update
    source: {PAGES_URL}/firmware/${{firmware_manifest_slug}}/manifest.json
"""

# Regex patterns for parsing include lines inside the packages: block
# Matches:  key: !include ../../path/to/file.yaml
RE_SIMPLE_INCLUDE = re.compile(
    r'^(\s+)(\S+):\s+!include\s+(.*?)\s*$'
)
# Matches:  key: !include { file: ../../path, vars: { ... } }
RE_VARS_INCLUDE = re.compile(
    r'^(\s+)(\S+):\s+!include\s*\{\s*file:\s*(.*?),\s*vars:\s*(\{.*?\})\s*\}\s*$'
)


def read_pin(yaml_path: str) -> str:
    """Read the upstream pin from community/upstream-ref.txt."""
    # Walk up from the yaml file to find the repo root containing community/
    search = os.path.dirname(os.path.abspath(yaml_path))
    for _ in range(10):
        candidate = os.path.join(search, "community", "upstream-ref.txt")
        if os.path.isfile(candidate):
            return open(candidate).read().strip()
        parent = os.path.dirname(search)
        if parent == search:
            break
        search = parent
    # Fallback: try relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ref_file = os.path.join(script_dir, "..", "upstream-ref.txt")
    if os.path.isfile(ref_file):
        return open(ref_file).read().strip()
    raise FileNotFoundError("Cannot find community/upstream-ref.txt")


def is_already_converted(content: str) -> bool:
    """Check if the file is already in remote-include form."""
    return "upstream_a:" in content


def parse_include_line(line: str):
    """
    Parse a line inside the packages: block.
    Returns one of:
      ('remote', path)           - simple remote include (../../...)
      ('remote_vars', path, vars_str) - remote include with vars
      ('local', key, path)       - local include (device/...)
      ('other', line)            - comment or non-include line
    """
    # Try vars-form first (more specific)
    m = RE_VARS_INCLUDE.match(line)
    if m:
        _indent, _key, file_path, vars_str = m.groups()
        file_path = file_path.strip()
        if file_path.startswith("../../"):
            remote_path = file_path[len("../../"):]
            return ('remote_vars', remote_path, vars_str.strip())
        else:
            return ('local', _key, line)

    # Try simple include
    m = RE_SIMPLE_INCLUDE.match(line)
    if m:
        _indent, key, path = m.groups()
        path = path.strip()
        if path.startswith("../../"):
            remote_path = path[len("../../"):]
            return ('remote', remote_path)
        else:
            return ('local', key, line)

    return ('other', line)


def convert_packages_content(content: str, pin: str) -> str:
    """
    Convert the packages.yaml content from upstream relative-include form
    to remote-include form.
    """
    if is_already_converted(content):
        return content

    lines = content.split('\n')

    # Find the packages: line
    packages_idx = None
    for i, line in enumerate(lines):
        if line.rstrip() == 'packages:':
            packages_idx = i
            break

    if packages_idx is None:
        # No packages: block found, return unchanged
        return content

    # Everything before packages: (including the line itself)
    pre_lines = lines[:packages_idx + 1]

    # Parse lines after packages:
    pkg_lines = lines[packages_idx + 1:]

    # Find where the packages block ends (next top-level key or EOF)
    pkg_block_end = len(pkg_lines)
    for i, line in enumerate(pkg_lines):
        # A non-empty line with no leading whitespace that isn't a comment
        # signals end of the packages block
        if line and not line[0].isspace() and not line.startswith('#'):
            pkg_block_end = i
            break

    pkg_block = pkg_lines[:pkg_block_end]
    after_block = pkg_lines[pkg_block_end:]

    # Parse the packages block into entries
    entries = []  # list of ('remote', path) | ('remote_vars', path, vars) | ('local', key, line) | ('comment', line)

    for line in pkg_block:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            # Comments and blank lines - skip them (they'll be regenerated structurally)
            continue

        parsed = parse_include_line(line)
        entries.append(parsed)

    # Now group entries: consecutive remote entries form one upstream block,
    # local entries break the run
    output_lines = list(pre_lines)
    upstream_idx = 0  # for upstream_a, upstream_b, ...

    def emit_upstream_block(remote_entries):
        """Emit an upstream_X block from a list of remote entries."""
        nonlocal upstream_idx
        letter = chr(ord('a') + upstream_idx)
        upstream_idx += 1
        output_lines.append(f"  upstream_{letter}:")
        output_lines.append(f"    url: {UPSTREAM_URL}")
        output_lines.append(f"    ref: {pin}")
        output_lines.append(f"    refresh: 1d")
        output_lines.append(f"    files:")
        for entry in remote_entries:
            if entry[0] == 'remote':
                output_lines.append(f"      - {entry[1]}")
            elif entry[0] == 'remote_vars':
                output_lines.append(f"      - path: {entry[1]}")
                output_lines.append(f"        vars: {entry[2]}")

    current_remote_run = []

    for entry in entries:
        if entry[0] in ('remote', 'remote_vars'):
            current_remote_run.append(entry)
        elif entry[0] == 'local':
            # Flush any pending remote run
            if current_remote_run:
                emit_upstream_block(current_remote_run)
                current_remote_run = []
            # Emit local include
            key = entry[1]
            # Re-extract the include path from the original line
            original_line = entry[2]
            m = RE_SIMPLE_INCLUDE.match(original_line)
            if m:
                _, _, path = m.groups()
                output_lines.append(f"  {key}: !include {path.strip()}")
            else:
                # Vars-form local (unlikely but handle)
                output_lines.append(f"  {original_line.strip()}")
        # 'other' entries (shouldn't happen after filtering comments)

    # Flush any remaining remote run
    if current_remote_run:
        emit_upstream_block(current_remote_run)
        current_remote_run = []

    # Add trailing newline after packages block
    output_lines.append("")

    # Check if community overrides already exist in the after_block
    after_text = '\n'.join(after_block)
    has_overrides = "# --- community hosting overrides ---" in after_text

    if not has_overrides:
        output_lines.append(COMMUNITY_OVERRIDES)
    else:
        # Keep existing content after packages block
        output_lines.extend(after_block)

    result = '\n'.join(output_lines)
    # Ensure single trailing newline
    result = result.rstrip('\n') + '\n'
    return result


def convert_file(path: str) -> None:
    """Convert a packages.yaml file in-place."""
    pin = read_pin(path)
    content = open(path, 'r').read()
    converted = convert_packages_content(content, pin)
    if converted != content:
        with open(path, 'w') as f:
            f.write(converted)
        print(f"Converted: {path}")
    else:
        print(f"No changes needed: {path}")


# =============================================================================
# Self-test
# =============================================================================

SELF_TEST_FIXTURE = """\
substitutions:
  device_slug: "guition-esp32-s3-4848s040"
  firmware_manifest_slug: "guition-esp32-s3-4848s040"
  firmware_version: "dev"

packages:
  entity_names:    !include ../../common/config/entity_names.yaml
  device:          !include device/device.yaml
  icons:           !include ../../common/assets/icons.yaml
  fonts_device:    !include device/fonts.yaml
  button_theme:    !include ../../common/theme/button.yaml
  colors:          !include ../../common/config/colors.yaml
  button_order:    !include ../../common/config/button_order.yaml
  display_config:  !include ../../common/config/display.yaml
  btn_1:           !include { file: ../../common/config/button_template_4chunk.yaml, vars: { num: "1" } }
  btn_2:           !include { file: ../../common/config/button_template_4chunk.yaml, vars: { num: "2" } }
  btn_3:           !include { file: ../../common/config/button_template_4chunk.yaml, vars: { num: "3" } }
  btn_4:           !include { file: ../../common/config/button_template_4chunk.yaml, vars: { num: "4" } }
  btn_5:           !include { file: ../../common/config/button_template_4chunk.yaml, vars: { num: "5" } }
  btn_6:           !include { file: ../../common/config/button_template_4chunk.yaml, vars: { num: "6" } }
  btn_7:           !include { file: ../../common/config/button_template_4chunk.yaml, vars: { num: "7" } }
  btn_8:           !include { file: ../../common/config/button_template_4chunk.yaml, vars: { num: "8" } }
  btn_9:           !include { file: ../../common/config/button_template_4chunk.yaml, vars: { num: "9" } }
  connectivity:    !include ../../common/addon/connectivity.yaml
  time_sync:       !include ../../common/addon/time.yaml
  backlight:       !include ../../common/addon/backlight.yaml
  bl_schedule:     !include ../../common/addon/backlight_schedule.yaml
  network:         !include ../../common/addon/network.yaml
  memory_diag:     !include ../../common/addon/memory_diagnostics.yaml
  fw_update:       !include ../../common/addon/firmware_update.yaml
  screen_loading:  !include ../../common/device/screen_loading.yaml
  screen_wifi:     !include ../../common/device/screen_wifi_setup.yaml
  screen_ha:       !include ../../common/device/screen_ha_setup.yaml
  screen_ha_act:   !include ../../common/device/screen_ha_actions.yaml
  screen_setup:    !include ../../common/device/screen_button_setup.yaml
  screen_clock:    !include ../../common/device/screen_clock.yaml
  screen_art:      !include ../../common/device/screen_cover_art.yaml
  image_cards:     !include ../../common/device/image_cards_1.yaml
  lvgl:            !include device/lvgl.yaml
  sensors:         !include device/sensors.yaml
"""


def self_test():
    """Run embedded self-tests."""
    pin = "v2.6.3"
    print("Running self-test...")

    # Test 1: Convert the fixture
    result = convert_packages_content(SELF_TEST_FIXTURE, pin)

    # Check upstream_a exists
    assert "upstream_a:" in result, "Missing upstream_a block"
    print("  ✓ upstream_a present")

    # Check we have upstream_b and upstream_c (device and fonts_device break the runs)
    assert "upstream_b:" in result, "Missing upstream_b block"
    assert "upstream_c:" in result, "Missing upstream_c block"
    print("  ✓ upstream_b and upstream_c present")

    # Check 9 vars entries
    vars_count = result.count("vars: { num:")
    assert vars_count == 9, f"Expected 9 vars entries, got {vars_count}"
    print("  ✓ 9 button vars entries")

    # Check interleave order: local includes between upstream blocks
    assert "  device: !include device/device.yaml" in result, "Missing device local include"
    assert "  fonts_device: !include device/fonts.yaml" in result, "Missing fonts_device local include"
    assert "  lvgl: !include device/lvgl.yaml" in result, "Missing lvgl local include"
    assert "  sensors: !include device/sensors.yaml" in result, "Missing sensors local include"
    print("  ✓ Local includes correctly interleaved")

    # Check ordering: upstream_a before device, device before upstream_b, etc.
    a_pos = result.index("upstream_a:")
    device_pos = result.index("device: !include device/device.yaml")
    b_pos = result.index("upstream_b:")
    fonts_pos = result.index("fonts_device: !include device/fonts.yaml")
    c_pos = result.index("upstream_c:")
    lvgl_pos = result.index("lvgl: !include device/lvgl.yaml")
    sensors_pos = result.index("sensors: !include device/sensors.yaml")
    assert a_pos < device_pos < b_pos < fonts_pos < c_pos < lvgl_pos < sensors_pos, \
        "Incorrect ordering of blocks"
    print("  ✓ Correct interleave order")

    # Check community overrides
    assert "web_server:" in result, "Missing web_server override"
    assert "# --- community hosting overrides ---" in result, "Missing overrides comment"
    assert PAGES_URL in result, "Missing pages URL"
    assert "!extend firmware_update" in result, "Missing firmware update override"
    print("  ✓ Community hosting overrides present")

    # Check upstream URL and ref
    assert UPSTREAM_URL in result, "Missing upstream URL"
    assert f"ref: {pin}" in result, "Missing ref pin"
    assert "refresh: 1d" in result, "Missing refresh"
    print("  ✓ Upstream URL/ref/refresh correct")

    # Test 2: Idempotence - converting again should be a no-op
    result2 = convert_packages_content(result, pin)
    assert result2 == result, "Idempotence check failed: second conversion changed the output"
    print("  ✓ Idempotent (second pass is no-op)")

    print("\nAll self-tests passed! ✓")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <packages.yaml>")
        print(f"       {sys.argv[0]} --self-test")
        sys.exit(1)

    if sys.argv[1] == "--self-test":
        self_test()
    else:
        path = sys.argv[1]
        if not os.path.isfile(path):
            print(f"Error: File not found: {path}")
            sys.exit(1)
        convert_file(path)


if __name__ == "__main__":
    main()
