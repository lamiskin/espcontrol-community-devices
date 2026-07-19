# Adding a Device

Step-by-step guide for porting a new device to the community repo.

## Prerequisites

- ESPHome installed locally (for compile testing)
- Python 3.10+
- The device hardware in hand (compile-only PRs are accepted as **Untested**)

## 1. Copy the closest existing device

Pick the device directory in this repo (or from an upstream PR) whose chip family
and resolution are closest to yours. Copy the entire directory:

```bash
cp -r devices/guition-esp32-s3-jc3248w535 devices/<your-slug>
```

Use a slug matching the pattern `<brand>-<chip>-<model>`, all lowercase with
hyphens.

## 2. Understand each file's role

Every device directory contains:

| File | Purpose |
|------|---------|
| `esphome.yaml` | User-facing entry point — device name, WiFi, remote package ref |
| `packages.yaml` | Include manifest — references upstream common files + local device files |
| `device/device.yaml` | Board, display driver, touchscreen, GPIO pin definitions |
| `device/fonts.yaml` | Font declarations sized for the display resolution |
| `device/lvgl.yaml` | Main page layout (grid, styles, button objects) |
| `device/sensors.yaml` | Touch, brightness, and diagnostic sensor definitions |

For deeper detail on each layer, see the upstream
[devices-and-builds.md](https://github.com/jtenniswood/espcontrol/blob/main/dev-docs/devices-and-builds.md).

## 3. Adapt device files

Edit the files in `devices/<your-slug>/device/` for your hardware:

- **device.yaml** — set the correct board, display driver, resolution, pin map
- **fonts.yaml** — scale font sizes to your resolution
- **lvgl.yaml** — adjust grid rows/cols and layout to match your slot count
- **sensors.yaml** — match your touch controller and sensor pins

Update `esphome.yaml` to point its remote package URL at your new slug:

```yaml
packages:
  setup:
    url: https://github.com/lamiskin/espcontrol-community-devices/
    file: devices/<your-slug>/packages.yaml
    refresh: 1s
```

## 4. Convert packages.yaml

If you started from an upstream PR that uses relative `!include ../../common/...`
paths, convert them to remote-include form:

```bash
python3 community/scripts/convert_packages.py devices/<your-slug>/packages.yaml
```

This rewrites relative includes into `upstream_a/b/c` blocks pinned at the
current ref (from `community/upstream-ref.txt`) and appends the community
hosting overrides.

If your `packages.yaml` is already in remote-include form (copied from this
repo), the script detects that and makes no changes.

## 5. Parity exceptions

Some upstream includes may not apply to your hardware. Common exceptions:

- **Voice/audio** — if your device has no speaker/mic, omit voice-related
  substitutions and set `voice_interaction_active_condition: "false"`
- **Image cards** — if PSRAM is too limited, reduce `imageSlots` in the
  catalog entry
- **Cover art live updates** — set `cover_art_live_image_updates: "false"` for
  displays that can't decode JPEG in real-time

Document any parity gaps in your PR description.

## 6. Write a catalog-fragment entry

Open `community/catalog-fragment.json` and add your device under the `"devices"`
object. Copy the structure from the existing reference device and adapt:

- `profiles.platform` — `esp32-s3` or `esp32-p4`
- `profiles.modal` — layout profile for your resolution
- `config.slots` — number of card slots your grid supports
- `config.public` — human-readable name, screen size, resolution, orientation
- `config.layout` — cols, rows, firmwareGrid
- `config.web` — web configurator dimensions and spacing

## 7. Local compile test

Run the full assembly to verify your device compiles cleanly against the pinned
upstream:

```bash
python3 community/scripts/assemble.py --skip-web
```

This clones upstream, overlays your device, merges the catalog, runs generators
and validators. A successful run means CI will also pass.

For faster iteration on just ESPHome compilation (after initial assembly):

```bash
cd .assembly
esphome compile devices/<your-slug>/esphome.yaml
```

## 8. Hardware evidence

Every device submission must include photo or video proof of hardware-tested
operation. Attach evidence to your PR showing:

- The device booting with your firmware
- Touch interaction working
- At least one card rendering correctly

Compile-only submissions are accepted with **Untested** status — the device
won't be marked **Working** in STATUS.md until hardware evidence is provided.

## 9. Add STATUS.md row

Add a row to `community/STATUS.md`:

```markdown
| Your Device Name | your-device-slug | Untested | community-v0.x.x-upstream.v2.6.3 | @your-github |
```

## 10. Open a PR

- Add a policy block for your slug in `community/DEVICES_POLICY.md` (same PR)
- Use `Co-authored-by: Name <email>` in the commit message for all contributors
- Fill out the PR template checklist

CI will run policy checks, include-parity checks, and an assembly compile.
Once hardware evidence is provided and reviewed, the status moves to **Working**.
