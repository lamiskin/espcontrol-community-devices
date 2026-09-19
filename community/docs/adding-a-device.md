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

Note: the nested includes inside `device/*.yaml` files (font glyph lists,
`core_infra.yaml`, `button_widget.yaml`) stay as relative `../../../common/...`
paths — those resolve against the repo-root `common/` directory, which contains
vendored copies of exactly those upstream files (see `common/VENDOR_MANIFEST.json`).
If your device references a `common/` file that isn't vendored yet, CI's
"Vendored common check" will tell you; fix it by running
`python3 community/scripts/vendor_common.py --source .assembly` and committing
the result.

## 5. Parity exceptions

Some upstream includes may not apply to your hardware. Common exceptions:

- **Voice/audio** — if your device has no speaker/mic, omit voice-related
  substitutions and set `voice_interaction_active_condition: "false"`
- **Image cards** — if PSRAM is too limited, reduce `imageSlots` in the
  catalog entry
- **Cover art live updates** — set `cover_art_live_image_updates: "false"` for
  displays that can't decode JPEG in real-time

If your device includes a different set of `common/` paths than the chip
family's reference device, `check_include_parity.py` will fail. If the
difference is intentional (one of the cases above, or similar), record it in
`devices/<slug>/parity-exceptions.txt` — one `common/` path per line, with a
comment explaining why. See an existing example under `devices/*/` for the
format.

**If the exception means this device does less than a sibling device on the
same chip family** — fewer image slots, a disabled feature, anything a user
would notice is missing compared to another community device of the same
platform — also add a `config.capabilityGaps` entry for it in
`catalog-fragment.json` (step 6): `{"feature": "...", "reason": "..."}`.
`generate_docs.py` turns that into a warning on the device's public docs
page, and `check_capability_docs.py` fails CI if a device's capability
numbers fall behind a sibling's without one. This is how a user browsing the
device list finds out *before* installing that (for example) Camera Cards
aren't available on their board, instead of discovering it missing with no
explanation. Don't skip this step because the gap "seems obvious" from the
hardware spec — it isn't obvious to someone comparing devices on the docs
site.

**Leaving `capabilityGaps` empty is a claim, not just silence.** If your
device has no gaps, `generate_docs.py` puts an explicit "Full upstream
feature parity" confirmation on its docs page — there's no neutral third
option where the page just says nothing. Don't leave it empty because you
didn't check; only leave it empty once you've actually confirmed this
device carries every upstream feature its sibling devices do (step 2's
diff against the chip family's reference device is what that confirmation
should be based on).

Document any parity gaps in your PR description too, so a reviewer isn't
left to reconstruct the reasoning from the diff.

## 6. Write a catalog-fragment entry

Open `community/catalog-fragment.json` and add your device under the `"devices"`
object. Copy the structure from the existing reference device and adapt:

- `profiles.platform` — `esp32-s3` or `esp32-p4`
- `profiles.modal` — layout profile for your resolution
- `config.slots` — number of card slots your grid supports
- `config.public` — human-readable name, screen size, resolution, orientation
- `config.layout` — cols, rows, firmwareGrid
- `config.web` — web configurator dimensions and spacing
- `config.capabilityGaps` — only if step 5 applies: `[{"feature": "...",
  "reason": "..."}]` for anything this device does less of than a sibling
  device on the same chip family

## 7. Register the device

A device isn't fully wired up just by having a directory and a catalog
entry — several more files have to reference the same slug before assembly,
CI, or the docs site will treat it as real.

Add your slug to the `"devices"` array in `community/devices.json`, keeping
the array **alphabetically sorted**:

```json
{"devices": ["...", "your-device-slug", "..."]}
```

This is easy to miss and **not optional** — `community/scripts/assemble.py`
only copies `devices/<slug>/` into the build tree for slugs listed here.
`catalog-fragment.json` entries are merged unconditionally regardless of this
list, so a slug present in the fragment but missing from `devices.json` gets
a catalog entry whose `fonts.yaml` (and every other device file) is never
overlaid — the validator then reports "unknown font id" for every id in a
perfectly correct `fonts.yaml`, because the file was never read. If you hit
that error, this file is the first place to check.

Also add:

- `builds/<slug>.yaml` and `builds/<slug>.factory.yaml` — dev/CI and
  factory-image build profiles. ESP32-P4 devices also need
  `builds/<slug>.recovery.yaml`, which repairs the onboard ESP32-C6 WiFi
  co-processor.
- An entry for your device in `community/device-labels.json` — but don't
  hand-edit it, it's generated (see below).

`community/scripts/check_status_consistency.py` enforces that every slug in
`devices.json` has a matching STATUS.md row, device directory, build
profiles, catalog-fragment entry, and DEVICES_POLICY.md block, and that
`devices.json` stays sorted:

```bash
python3 community/scripts/check_status_consistency.py
```

Then regenerate the derived docs and issue-label files so they pick up the
new device:

```bash
python3 community/scripts/generate_docs.py
python3 community/scripts/generate_issue_labels.py
```

The first regenerates the per-device docs pages, the home-page device table,
and the docs sidebar from `catalog-fragment.json` + `STATUS.md`. The second
regenerates `community/device-labels.json` and the bug-report issue template
from `devices.json` + `catalog-fragment.json` — this is what actually
populates `device-labels.json`. CI runs both with `--check` and fails the
build if the regenerated output wasn't committed.

## 8. Local compile test

Run the full assembly to verify your device compiles cleanly against the pinned
upstream:

```bash
python3 community/scripts/assemble.py --skip-web
```

This clones upstream, overlays your device, merges the catalog, runs generators
and validators. A successful run means CI will also pass.

You will see `Validator warning: 'python3 scripts/check_device_profiles.py'
exited with code 1` in the output — that is expected and non-fatal (see
[`upstream-ref-bump.md`'s Gotchas](upstream-ref-bump.md#gotchas)). It asserts
upstream's own hardcoded device-slug fixture, which can never account for
community devices; `assemble.py` treats it as advisory for exactly this
reason. Don't chase it.

For faster iteration on just ESPHome compilation (after initial assembly):

```bash
cd .assembly
esphome compile devices/<your-slug>/esphome.yaml
```

## 9. Hardware evidence

Every device submission must include photo or video proof of hardware-tested
operation. Attach evidence to your PR showing:

- The device booting with your firmware
- Touch interaction working
- At least one card rendering correctly

Compile-only submissions are accepted with **Untested** status — the device
won't be marked **Working** in STATUS.md until hardware evidence is provided.

**Getting a working UI screenshot before your PR is merged:** the default
build points the panel's web UI at `js_url`, which loads `webserver/www.js`
live from GitHub Pages. That site only rebuilds from `main`, so it has no
entry for your device's profile until your PR merges — flashing the default
build pre-merge will boot fine but show `Unsupported EspControl device
profile: <your-slug>` in the browser console instead of a UI. That's
expected, not a bug in your device config (see community issue #133).

To get a real, working UI for your evidence screenshot, build and flash the
**factory** variant instead, which embeds the bundle via `js_include` rather
than fetching it live:

```bash
python3 community/scripts/assemble.py   # no --skip-web this time
cd .assembly
# Every builds/*.yaml and builds/*.factory.yaml points its espcontrol
# component source at file:///config with ref: HEAD — a placeholder for the
# Home Assistant ESPHome dashboard's local /config mount, not a real path.
# Compiling directly with the CLI needs it rewritten first (this is exactly
# what community-ci.yml's compile job does before it invokes esphome), or
# `esphome compile` fails with "fatal: '/config' does not appear to be a
# git repository" (see community issue #133).
sed -i "s|file:///config|file://$(pwd)|g" builds/<your-slug>.factory.yaml
esphome compile builds/<your-slug>.factory.yaml
```

This embeds a `www.js` built from your own working tree, so it already knows
about your device, directly into the firmware — no need to wait for merge.

## 10. Add STATUS.md row

Add a row to `community/STATUS.md`:

```markdown
| Your Device Name | your-device-slug | Untested | community-v0.x.x-upstream.v2.6.3 | @your-github |
```

## 11. Open a PR

- Add a policy block for your slug in `community/DEVICES_POLICY.md` (same PR)
- Use `Co-authored-by: Name <email>` in the commit message for all contributors
- Fill out the PR template checklist

CI will run policy checks, include-parity checks, and an assembly compile.
Once hardware evidence is provided and reviewed, the status moves to **Working**.
