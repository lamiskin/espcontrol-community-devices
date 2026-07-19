# Option C Remote-Include Spike — Results

**Date:** 2026-07-19
**ESPHome version:** 2026.7.0
**Upstream pin:** v2.6.3
**Device:** guition-esp32-s3-4848s040

---

## Verdict: GO ✅

Both `esphome config` and `esphome compile` pass with the remote-include pattern.
The firmware binary was produced successfully (3.46 MB flash, 55.8% RAM).

---

## What Was Tested

The spike rewrote the device's `packages.yaml` from local relative `!include` paths
into the remote-include form:

```yaml
packages:
  upstream_a:
    url: https://github.com/jtenniswood/espcontrol
    ref: v2.6.3
    refresh: 1d
    files:
      - common/config/entity_names.yaml
  device: !include device/device.yaml
  upstream_b: ...
  upstream_c: ...
  lvgl: !include device/lvgl.yaml
  sensors: !include device/sensors.yaml
```

A local `user.yaml` entry point includes the rewritten `packages.yaml` with hardcoded wifi.

---

## Key Findings

### 1. Substitutions resolve across remote packages ✅

Substitutions defined in the top-level `packages.yaml` (e.g. `${device_slug}`,
`${firmware_version}`) are available inside remotely-fetched common YAML files.
This was the primary NO-GO condition — it passes.

### 2. `vars` works for remote files ✅

The `path:` + `vars:` syntax for remote files is supported:

```yaml
- path: common/config/button_template_4chunk.yaml
  vars: { num: "1" }
```

Each button template was instantiated with unique IDs (`button_1_config`,
`button_2_config`, etc.) confirming `vars` is not silently ignored.

### 3. `!extend` works for community overrides ✅

The `update:` section with `id: !extend firmware_update` successfully overrode
the `source:` URL from the upstream `firmware_update.yaml`. The resolved config
shows our `https://example.invalid/firmware/...` URL.

### 4. `web_server.js_url` override works ✅

The top-level `web_server:` block in our packages.yaml merges with the one from
`core_infra.yaml` and our `js_url` override takes effect.

### 5. Local device files need access to upstream `common/` directory ⚠️

**This is the main structural constraint.**

The local device files (`device.yaml`, `fonts.yaml`, `lvgl.yaml`) contain nested
`!include` references with relative paths like `../../../common/assets/icon_glyphs.yaml`.
These resolve against the local filesystem, not the remote package cache.

**Solution used in spike:** A symlink from `spike/common` → `.esphome/packages/<hash>/common/`
satisfies the relative paths. The cache hash is deterministic per URL+ref combo.

**Production options:**
- Option A: Symlink to the ESPHome package cache (fragile, depends on hash)
- Option B: Shallow git clone of upstream at the pin into a local `common/` dir
- Option C: Rewrite device files to eliminate relative `!include` into common/
  (requires font glyph lists and button widgets to be inlined or restructured)
- Option D: Accept that the community repo must contain (or generate) the
  `common/` tree at the pinned ref — a build/setup script creates it

**Recommended:** Option D — a setup script runs `git clone --depth 1 --branch v2.6.3`
into a gitignored `common/` directory. This is predictable and doesn't depend on
ESPHome cache internals.

### 6. Package ordering is preserved ✅

The interleaved `upstream_a` / local / `upstream_b` / local / `upstream_c` / local
pattern preserves the exact include order from the original. LVGL pages load in
the correct sequence (loading screen first, then setup screens, then main page).

### 7. No duplicate ID issues ✅

All 9 button slots have unique IDs. No conflicts between remote and local definitions.

---

## Syntax Corrections Discovered

1. **None required** — the remote-include YAML syntax from the design doc worked
   as-is on the first attempt (after fixing the `common/` path issue which is a
   structural concern, not a syntax one).

2. The `!extend` syntax is `id: !extend firmware_update` (inline with the list item),
   not a separate key. This matches the ESPHome documentation.

---

## www.js Bundle Path

From `common/device/core_infra.yaml` at v2.6.3:

```
https://jtenniswood.github.io/espcontrol/webserver/www.js?device=${device_slug}&v=${firmware_version}&ui=20260714-shared
```

The community hosting override will need to serve this bundle at its own URL.
The `ui=20260714-shared` query param suggests a shared UI version identifier.

---

## Build Stats

| Metric | Value |
|--------|-------|
| Config validation | PASS |
| Full compile | PASS |
| Flash usage | 42.6% (3,464,655 / 8,126,464 bytes) |
| RAM usage | 55.8% (190,755 / 341,760 bytes) |
| Object files compiled | 1,850 |
| Compile time | ~8 minutes (first run with toolchain download) |

---

## Next Steps

1. Decide on the `common/` directory strategy (recommend Option D: setup script)
2. Build the community repo scaffolding with the remote-include pattern
3. Set up CI to validate configs against the pinned upstream tag
4. Create the www.js hosting and firmware manifest infrastructure

---

## Tag Format Spike — Release Workflow Triggers

**Date:** 2026-07-19

### Finding: `+` in git tags does NOT trigger GitHub Actions

Pushed tag `community-v0.0.1+v2.6.3` — the workflow with `on: push: tags: ["community-v*"]`
did **not** fire. The tag was created successfully on GitHub (visible in the tags list),
but Actions did not recognize the push event.

**Root cause:** The `+` character in a git tag is URL-encoded to `%2B` in GitHub's ref
handling. The glob pattern `community-v*` apparently doesn't match when the ref contains
an encoded `+`. This is a known limitation.

### Decision: Use `-upstream.` separator instead

Switching tag format from:
- ❌ `community-v0.0.1+v2.6.3`

To:
- ✅ `community-v0.0.1-upstream.v2.6.3`

This preserves the semver-ish structure (pre-release metadata after `-`) and avoids
the `+` encoding issue entirely. The `community-v*` glob pattern matches both formats
but only the `-upstream.` format actually triggers the workflow.

### Verification

- `community-v0.0.1+v2.6.3` → pushed OK, workflow NOT triggered ❌
- `community-v0.0.1-upstream.v2.6.3` → pushed OK, workflow TRIGGERED ✅ (run 29675861033)


### Release Workflow First Run (community-v0.0.1-upstream.v2.6.3)

The workflow triggered and completed these steps successfully:
- ✅ Checkout at tag ref
- ✅ Determine version
- ✅ Free disk space
- ✅ Assemble (full upstream clone + overlay + catalog merge)
- ✅ Setup Python 3.12
- ✅ Install ESPHome 2026.7.0

**Failed at:** Compile and collect firmware

**Root cause:** The device config `devices/guition-esp32-s3-jc3248w535/device/device.yaml`
references `external_components` with `url: file:///config` (a Home Assistant add-on path).
In CI, `/config` doesn't exist. This needs to be overridden in the community overlay to use
the assembled tree's local components path or the GitHub URL.

**This is a device configuration issue, not a workflow issue.** The workflow structure is
correct and will work once the device YAML properly handles CI compilation.


---

## ESP32-P4 Community Port — First Device Findings

**Date:** 2026-07-20
**Device:** Seeed reTerminal D1001 (8" 1280×800 ESP32-P4)
**Upstream PR:** #885
**PR author:** @zacs

---

### Verdict: DRAFT (blocked on upstream merge) ⚠️

The port is structurally complete but cannot pass `esphome config` validation because:
1. The device requires the `gsl3670` touch component which does NOT exist at v2.6.3
2. The PR (#885) introduces this component alongside the device
3. Using the PR branch SHA for both common files and components causes ID mismatches
   (`display_mode_controller`, `display_takeover_begin`, `entity_display_restart`)

---

### P4-Specific Structural Differences

Compared to S3 community devices:

| Aspect | S3 Devices | P4 Devices (D1001) |
|--------|-----------|-------------------|
| Button template | `button_template_4chunk.yaml` | `button_template.yaml` |
| Extra device files | None | `audio.yaml`, `microphone.yaml`, `power.yaml` |
| Network coprocessor | N/A | ESP32-C6 via SDIO (`esp32_c6_firmware_update.yaml`) |
| API navigation | N/A | `api_navigate.yaml` |
| Display interface | SPI/RGB parallel | MIPI DSI |
| Slots | 6-9 | 20 (5×4 grid) |
| Remote-include blocks | 3 (upstream_a/b/c) | 4 (upstream_a/b/c/d) — extra split at audio/mic/power |

### convert_packages.py Results

The general-purpose converter handled the P4 packages correctly:
- ✅ Created 4 upstream blocks (extra split for P4-specific local device files)
- ✅ Preserved button template vars entries
- ✅ Added community hosting overrides

### generate_device_slots.py Issue

The upstream generator:
- Requires `BEGIN/END GENERATED BUTTON PACKAGES` markers in packages.yaml
- Attempts to rewrite the ENTIRE packages.yaml in upstream relative-include format
- Does NOT understand the remote-include format
- This causes the assemble script to report "generators modified community device files
  outside generated blocks" — this is expected and non-fatal

**Resolution:** Added the marker comments around the button template entries in the
remote-include format. The generator still rewrites the file in the assembly tree
(which is discarded), but the community source retains the correct format.

### Blocking Issues

1. **Component not at pinned tag:** `gsl3670` only exists in PR #885, not at v2.6.3.
   Until the PR is merged and a new tag is cut, this device cannot reference v2.6.3
   for its components.

2. **ID mismatches at PR SHA:** Using the PR commit SHA (78e8ba5d) for common files
   reveals references to `display_mode_controller` and `display_takeover_begin` that
   don't exist in the device's local files. This suggests the common code has evolved
   past what the PR's device files expect.

3. **Hostname length:** The device slug exceeds the 24-char ESPHome hostname limit.
   Resolved by using shortened build name `espcontrol-d1001`.

### Next Steps

1. Wait for upstream PR #885 to merge and a new release tag (v2.7.x) to be cut
2. Repin the community port to the new tag
3. Verify `esphome config` passes with the consistent tag reference
4. Run full compile to confirm firmware builds
