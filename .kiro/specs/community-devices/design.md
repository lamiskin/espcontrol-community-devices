# Design Document

## Overview

`espcontrol-community` is a **thin overlay repository**. It contains only
community-owned device configs and tooling. Upstream code is consumed three ways, none
of which copy files into this repo:

1. **At user compile time** — ESPHome remote git packages pull upstream `common/*.yaml`
   files at a pinned ref; `external_components` pulls `components/` from upstream git at
   the same ref.
2. **At device runtime** — the panel loads the web configurator (`www.js`) and OTA
   manifests from **this repo's** GitHub Pages (URLs overridden per device), because
   device profiles are baked into `www.js` at build time and upstream's copy doesn't
   know community devices.
3. **In CI only** — a full upstream checkout is assembled with the overlay copied in, to
   run upstream's generators/validators, build `www.js`, and compile firmware. The
   assembled tree is throwaway; it is never committed.

Nothing here requires any change to the upstream repository. All facts below were
verified against upstream at commit `b4eefbfd` (2026-07-18); re-verify paths if the pin
moves far.

### Verified upstream facts this design depends on

| Fact | Where verified |
|---|---|
| ESPHome version pin `2026.6.5` | `.github/esphome.env` |
| Device dir shape: `esphome.yaml`, `dev.yaml`, `packages.yaml`, `device/{device,fonts,lvgl,sensors}.yaml` | `devices/guition-esp32-s3-4848s040/` |
| `packages.yaml` includes `../../common/*.yaml` + local `device/*.yaml`; load order matters (loading screen must be LVGL's first page) | same |
| Components fetched from git with substitutable `espcontrol_component_url`/`espcontrol_component_ref` | `devices/*/device/device.yaml` |
| Web UI: `js_url: https://jtenniswood.github.io/espcontrol/webserver/www.js?device=${device_slug}&v=${firmware_version}&ui=…` | `common/device/core_infra.yaml` line ~121 |
| Device profiles are compile-time constants in www.js (`__ESPCONTROL_DEVICE_PROFILES__`); `?device=` selects from the embedded record | `src/webserver/device_config.ts` |
| OTA updater: `update: - platform: http_request, id: firmware_update, source: https://jtenniswood.github.io/espcontrol/firmware/${firmware_manifest_slug}/manifest.json` | `common/addon/firmware_update.yaml` line ~168 |
| Fonts are remote (`gfonts://…`, CDN `${mdi_font_file}`) | `devices/*/device/fonts.yaml` |
| Generators: `python3 scripts/generate_device_manifest.py` (catalog → manifest), `python3 scripts/generate_device_slots.py` (manifest → generated YAML blocks), `python3 scripts/build.py [all|entities|contract|devices|icons|i18n|www] [--check]`; web bundle = `python3 scripts/build.py www` | `scripts/`, `package.json` |
| Validators: `check_device_manifest.py`, `check_device_matrix.py`, `check_device_profiles.py`, `build.py --check` | `package.json` `check:*:legacy` scripts |
| ESPHome remote packages support git `url` + `ref` + `files:` list + per-file `vars` | esphome.io/components/packages |
| Upstream catalog: `devices/catalog.json` (source of truth) → generated `devices/manifest.json` | `dev-docs/devices-and-builds.md` |

## Architecture

```
User's esphome.yaml
   └── remote package → THIS repo (clone) → devices/<slug>/packages.yaml
         ├── !include device/*.yaml            (local, in this repo's clone)
         ├── remote packages → upstream@PIN    (common/*.yaml, per-file vars)
         ├── external_components → upstream@PIN (components/)
         └── overrides: js_url + update.source → THIS repo's GitHub Pages

CI (assembly, throwaway):
   upstream@PIN checkout + copy overlay in + merge catalog fragment
     → generators → validators → build.py www → esphome compile builds/<slug>.yaml
```

Repository layout (paths mirror upstream so upstream-PR file copies land cleanly):

```
devices/<slug>/                  # community devices only
  esphome.yaml                   # user-facing entry (points at THIS repo)
  packages.yaml                  # remote-include form (see below)
  device/{device,fonts,lvgl,sensors}.yaml
builds/<slug>.yaml               # CI compile entry
builds/<slug>.factory.yaml       # factory image entry
community/
  upstream-ref.txt               # THE pin. One line, tag or SHA. e.g. v2.5.3
  devices.json                   # {"devices": ["<slug>", ...]}
  catalog-fragment.json          # device entries in upstream catalog.json schema
  STATUS.md                      # | Device | Slug | Status | Last verified | Owner |
  DEVICES_POLICY.md
  SPIKE.md
  scripts/assemble.py            # build the throwaway full tree
  scripts/convert_packages.py    # rewrite relative includes → remote-include form
  scripts/check_policy.py        # PR changed-files allowlist
  scripts/check_include_parity.py
  scripts/check_pin_consistency.py
  docs/adding-a-device.md
.github/workflows/community-{ci,nightly,ref-bump,release,pages}.yml
.github/PULL_REQUEST_TEMPLATE.md
.github/ISSUE_TEMPLATE/device-request.yml
README.md  LICENSE  NOTICE
```

## Components and Interfaces

### 1. Device packages.yaml — remote-include form (the core pattern)

Below is the exact conversion of upstream's `guition-esp32-s3-4848s040` device (the
reference for all S3 devices; the P4 reference is `guition-esp32-p4-jc1060p470`).
`<PIN>` is the literal content of `community/upstream-ref.txt`; `<PAGES>` is
`https://<ORG>.github.io/espcontrol-community`. Keep **all substitutions from the
original file unchanged** — only the `packages:` block and the two overrides change.
Package mapping order is load order; the three `upstream_*` entries interleave with
local includes to preserve upstream's original order exactly.

```yaml
substitutions:
  # ... copy the ENTIRE substitutions block from the upstream device's
  # packages.yaml at <PIN>, unchanged ...

packages:
  upstream_a:
    url: https://github.com/jtenniswood/espcontrol
    ref: <PIN>
    refresh: 1d
    files:
      - common/config/entity_names.yaml
  device: !include device/device.yaml
  upstream_b:
    url: https://github.com/jtenniswood/espcontrol
    ref: <PIN>
    refresh: 1d
    files:
      - common/assets/icons.yaml
  fonts_device: !include device/fonts.yaml
  upstream_c:
    url: https://github.com/jtenniswood/espcontrol
    ref: <PIN>
    refresh: 1d
    files:
      - common/theme/button.yaml
      - common/config/colors.yaml
      - common/config/button_order.yaml
      - common/config/display.yaml
      - path: common/config/button_template_4chunk.yaml
        vars: { num: "1" }
      - path: common/config/button_template_4chunk.yaml
        vars: { num: "2" }
      - path: common/config/button_template_4chunk.yaml
        vars: { num: "3" }
      - path: common/config/button_template_4chunk.yaml
        vars: { num: "4" }
      - path: common/config/button_template_4chunk.yaml
        vars: { num: "5" }
      - path: common/config/button_template_4chunk.yaml
        vars: { num: "6" }
      - path: common/config/button_template_4chunk.yaml
        vars: { num: "7" }
      - path: common/config/button_template_4chunk.yaml
        vars: { num: "8" }
      - path: common/config/button_template_4chunk.yaml
        vars: { num: "9" }
      - common/addon/connectivity.yaml
      - common/addon/time.yaml
      - common/addon/backlight.yaml
      - common/addon/backlight_schedule.yaml
      - common/addon/network.yaml
      - common/addon/memory_diagnostics.yaml
      - common/addon/firmware_update.yaml
      - common/device/screen_loading.yaml
      - common/device/screen_wifi_setup.yaml
      - common/device/screen_ha_setup.yaml
      - common/device/screen_ha_actions.yaml
      - common/device/screen_button_setup.yaml
      - common/device/screen_clock.yaml
      - common/device/screen_cover_art.yaml
  lvgl: !include device/lvgl.yaml
  sensors: !include device/sensors.yaml

# --- community hosting overrides (the including file wins over its packages) ---
web_server:
  js_url: <PAGES>/webserver/www.js?device=${device_slug}&v=${firmware_version}

update:
  - id: !extend firmware_update
    source: <PAGES>/firmware/${firmware_manifest_slug}/manifest.json
```

IMPORTANT for the implementer:

- The button-count and template file differ per device grid size. The 3x3 grid uses 9 ×
  `button_template_4chunk.yaml`. Always mirror what the ported device's ORIGINAL
  packages.yaml (or the reference device at `<PIN>`) uses — the generated block between
  `# BEGIN GENERATED BUTTON PACKAGES` / `# END GENERATED BUTTON PACKAGES` tells you the
  exact template file and count.
- The number of `upstream_*` split points is dictated by upstream's original include
  order (remote files can't interleave with local includes inside one package entry).
  If upstream's order changes at a new pin, re-derive the split from the reference
  device's packages.yaml at that pin.
- `!extend` syntax: `- id: !extend firmware_update` then the keys to override. If the
  compile rejects it, check the current syntax at
  https://esphome.io/guides/configuration-types/#extend and record the correction in
  `community/SPIKE.md`.
- In `device/device.yaml`, set `espcontrol_component_ref: "<PIN>"` (upstream defaults it
  to `main`).
- `devices/<slug>/esphome.yaml` mirrors upstream's but with
  `url: https://github.com/<ORG>/espcontrol-community/` and
  `file: devices/<slug>/packages.yaml`.
- `builds/<slug>.factory.yaml` mirrors upstream's but `dashboard_import` points at
  `github://<ORG>/espcontrol-community/devices/<slug>/esphome.yaml@main`.
- `builds/*.yaml` compile inside the ASSEMBLED tree (CI), so they keep upstream's
  relative-path style (`!include ../devices/<slug>/packages.yaml`,
  `js_include: "../docs/public/webserver/www.js"`, local `espcontrol_component_url:
  "file:///config"`) — copy the shape of upstream's `builds/guition-esp32-s3-4848s040*.yaml`
  and substitute the slug/names. NOTE: inside the assembled tree the device
  packages.yaml is the remote-include form; that is fine — remote packages work in any
  compile — but it will download from upstream even in CI. Acceptable; do not "fix" it.

### 2. `community/scripts/convert_packages.py`

Input: an upstream-style `packages.yaml` (relative includes). Output: remote-include
form per the pattern above. Algorithm:

1. Parse the `packages:` mapping preserving order (use `ruamel.yaml` or line-based
   parsing — the file uses custom tags like `!include`, so PyYAML needs
   `yaml.add_multi_constructor` or treat it as text; **line-based text transformation is
   acceptable and simpler**: match lines `^  \w+:\s+!include (\.\./\.\./)?(.+)$` and the
   `!include { file: ..., vars: { num: "N" } }` single-line form).
2. Lines whose target starts with `../../` → collect into consecutive runs; each run
   becomes one `upstream_<letter>` remote package entry (strip `../../`).
   Vars-form includes become `- path: <file>\n  vars: { num: "N" }` entries.
3. Lines whose target is local (`device/...`) → emit unchanged.
4. Read `<PIN>` from `community/upstream-ref.txt`; emit `url/ref/refresh` headers.
5. Append the `web_server:` and `update:` override blocks if not already present.
6. Idempotent: running on an already-converted file is a no-op (detect via presence of
   `upstream_a:`).

### 3. `community/scripts/assemble.py`

Builds the throwaway full tree at `.assembly/` (gitignored):

```
python3 community/scripts/assemble.py [--skip-checks]
```

1. Read `<PIN>` from `community/upstream-ref.txt`.
2. `git clone --depth 1 --branch <PIN> https://github.com/jtenniswood/espcontrol .assembly`
   (if `<PIN>` is a SHA: clone default branch, `git fetch origin <PIN>`, `git checkout <PIN>`).
   In GitHub Actions, prefer `actions/checkout` with `repository:`/`ref:`/`path: .assembly`.
3. Copy `devices/<slug>/` and `builds/<slug>*.yaml` for every slug in
   `community/devices.json` into `.assembly/` (fail if a target path already exists —
   means a slug collides with an official device).
4. Merge `community/catalog-fragment.json` into `.assembly/devices/catalog.json`:
   load both with `json`; inspect the catalog's structure at the pin (device entries live
   under a devices collection after the `profiles` section — **discover the exact key by
   reading the file**, do not hardcode blindly); append fragment entries at the END;
   fail if a slug already exists.
5. In `.assembly/`: `python3 scripts/generate_device_manifest.py` then
   `python3 scripts/generate_device_slots.py` then `python3 scripts/build.py devices`.
   If generators modify any community device file, print the diff and exit nonzero
   UNLESS the only changes are inside `BEGIN/END GENERATED` marker blocks (those are
   expected; copy them back to the overlay with `--sync-generated` flag).
6. Unless `--skip-checks`: `python3 scripts/check_device_manifest.py`,
   `python3 scripts/check_device_matrix.py`, `python3 scripts/check_device_profiles.py`
   (all inside `.assembly/`).
7. Web bundle: `npm ci && python3 scripts/build.py www` inside `.assembly/`; copy the
   produced shared bundle (find it under `docs/public/webserver/` — the `?ui=…-shared`
   naming in core_infra.yaml indicates a shared bundle output; locate the actual file
   produced by `build.py www` and record the path in SPIKE.md on first run) to
   `community-pages/webserver/www.js`. Verify a community slug appears in the bundle:
   `grep -q '<slug>' community-pages/webserver/www.js`.

### 4. `community/scripts/check_policy.py`

`python3 community/scripts/check_policy.py --base <sha> --head <sha>`
(CI passes `${{ github.event.pull_request.base.sha }}` / `head.sha`).
Get changed files via `git diff --name-only base...head`. Each changed path must match
one of:
- `devices/<slug>/**` or `builds/<slug>*.yaml` where `<slug>` ∈ `community/devices.json`
  (of the HEAD version — a PR adding a new device adds its slug in the same PR),
- `community/**`, `README.md`, `.github/**`.
Additionally, if `community/catalog-fragment.json` changed, every modified/added entry's
slug must be in the PR's `devices.json`. Exit nonzero with a clear message listing
violations.

### 5. `community/scripts/check_include_parity.py`

For each device: extract the set of `common/...` paths from its packages.yaml remote
entries. Compare against the reference device of the same chip family at `<PIN>`
(`guition-esp32-s3-4848s040` for `esp32-s3`, `guition-esp32-p4-jc1060p470` for
`esp32-p4`; chip family read from the device's catalog-fragment entry). Fetch reference:
`git -C .assembly show <PIN>:devices/<ref-slug>/packages.yaml` (or raw.githubusercontent
at the pin). Report missing/extra paths. Devices may declare intentional deviations in
`devices/<slug>/parity-exceptions.txt` (one path per line, with a trailing `# reason`).

### 6. `community/scripts/check_pin_consistency.py`

Every occurrence of an upstream `ref:` or `espcontrol_component_ref:` in
`devices/**` must equal the content of `community/upstream-ref.txt`. Grep-based; exit
nonzero listing mismatches.

### 7. GitHub Actions workflows

All jobs: `runs-on: ubuntu-latest`. Install ESPHome with
`pip install esphome==2026.6.5` (read the version from `.assembly/.github/esphome.env`
after assembly to stay in lockstep — parse `ESPHOME_VERSION=`). Cache: `actions/cache`
on `~/.platformio`, `~/.cache/pip`, and `.assembly/.esphome` keyed on
`(<PIN>, esphome-version)`. Expect 30–60+ min per device compile; set
`timeout-minutes: 120` on compile jobs.

- **community-ci.yml** — `on: pull_request`. Jobs: `policy` (check_policy.py) →
  `assemble` (assemble.py + parity + pin-consistency; upload `.assembly` as artifact is
  NOT needed — rerun assemble in the compile job, it's cheap vs compile) →
  `compile` (matrix over device slugs whose files the PR touched; each runs assemble
  then `cd .assembly && esphome compile builds/<slug>.yaml`).
- **community-nightly.yml** — `on: schedule: "0 6 * * *"` + `workflow_dispatch`.
  Matrix over ALL slugs in devices.json: assemble + compile `builds/<slug>.yaml`.
  Post-matrix job: for failures, `gh issue list --label broken --search "[broken] <slug>"`
  → create or comment (never duplicate); update STATUS.md row via committed change;
  successes flip Broken→Working. Commit STATUS changes with message
  `chore: nightly status update`.
- **community-ref-bump.yml** — `on: schedule: "0 4 * * 1"` + dispatch. Query latest
  upstream release: `gh api repos/jtenniswood/espcontrol/releases/latest --jq .tag_name`.
  If newer than `<PIN>`: branch `ref-bump/<tag>`, write `upstream-ref.txt`, run
  `python3 community/scripts/bump_refs.py` (small script: rewrite every `ref:`/
  `espcontrol_component_ref:` in `devices/**` to the new pin — reuse
  check_pin_consistency's discovery), run assemble + parity for drift report, compile
  all devices, open a PR (label `ref-bump`) whose body contains per-device compile
  results and the parity report. Never auto-merge.
- **community-release.yml** — `on: push: tags: ["community-v*"]`. Assemble; for each
  device: `esphome compile builds/<slug>.factory.yaml`; collect
  `.assembly/.esphome/build/**/firmware.factory.bin` and `firmware.ota.bin` (verify
  exact artifact names/paths from upstream's `release.yml` and
  `scripts/check_firmware_release.py` at the pin — mirror upstream's manifest JSON
  shapes for both ESP Web Tools and the OTA `update:` component); write
  `community-pages/firmware/<slug>/manifest.json`; `gh release create` with binaries.
- **community-pages.yml** — `on: workflow_run` after release, + dispatch. Publish
  `community-pages/` via `actions/upload-pages-artifact` + `actions/deploy-pages`:
  `index.html` (installer: one `<esp-web-tools-install-button>` per Working device,
  esp-web-tools loaded from unpkg CDN), `webserver/www.js`, `firmware/<slug>/manifest.json`.

### 8. Option B fallback (only if the spike fails — see requirements 7)

Same repo layout, two changes: (1) device `packages.yaml` keeps upstream's
relative-include form verbatim (no conversion, no remote packages — but KEEP the
`web_server:`/`update:` overrides and the pinned `espcontrol_component_ref`);
(2) a `community-dist.yml` workflow runs assemble.py and force-pushes `.assembly/` to a
protected `dist` branch; users' `esphome.yaml` references
`url: https://github.com/<ORG>/espcontrol-community/`, `ref: dist`. The ref-bump PR
gates dist regeneration exactly as it gates pin bumps in Option C.

## Data Models

- **`community/upstream-ref.txt`** — single line, e.g. `v2.5.3`. Tags or 40-char SHAs
  only; never `main`.
- **`community/devices.json`** — `{ "devices": ["<slug>", ...] }`, alphabetical.
- **`community/catalog-fragment.json`** — `{ "devices": { "<slug>": { ...exact upstream
  catalog.json device-entry schema at <PIN>... } } }`. Author each entry by copying the
  closest official device's entry from `.assembly/devices/catalog.json` and editing
  name/docsPath/screenSize/resolution/orientation/layout/rotation/platform profile refs.
- **STATUS.md row** — `| <Name> | <slug> | Working|Broken|Untested | community-vX.Y.Z+<pin> | @<gh-user> |`.

## Error Handling

Known failure modes and the prescribed response (do NOT improvise around these):

| Symptom | Meaning | Action |
|---|---|---|
| Substitution like `${device_slug}` unresolved in a remotely-included common file | Substitution scoping across remote packages broken | This is the spike's NO-GO condition. Stop, record in SPIKE.md, switch to Option B. |
| `vars` ignored for remote files (all buttons become btn "num" or duplicate ids) | Per-file vars unsupported in pinned ESPHome | NO-GO condition → Option B. |
| LVGL shows wrong first page / setup screens out of order | Load order broken by package split | Add more `upstream_*` split points to restore exact original order. If still broken → NO-GO. |
| `!extend firmware_update` rejected | Syntax drift | Check esphome.io configuration-types docs; fix syntax; record in SPIKE.md. Do not delete the override. |
| Generators rewrite community `packages.yaml` outside marker blocks | Assembly merge or catalog entry wrong | Diff, fix the catalog-fragment entry; never commit `.assembly` output wholesale. |
| GH runner disk/OOM during compile | ESP-IDF build too big | Add `df -h` diagnostics; free space with `rm -rf /usr/share/dotnet /opt/ghc` (standard runner-cleanup trick); add swap. |
| Nightly red after a merged ref bump that was green | Remote piece moved outside pinned scope (CDN font, gfonts) | Investigate the specific fetch; pin the asset (e.g. vendor the font URL version). |
| Upstream catalog.json structure changed at new pin | Fragment merge fails | Update assemble.py's merge to the new structure as part of the ref-bump PR. |

Standing rules: never edit files under `.assembly/` by hand and never commit that
directory (gitignore it in the repo root). Never point anything at upstream `main`.
Every workflow must be dispatchable (`workflow_dispatch`) for testing.

## Testing Strategy

- **Spike (first, gating):** convert reference device → `esphome compile` a user-style
  config on ESPHome 2026.6.5 → hardware flash by Lachlan (verify: boots to loading
  screen, WiFi setup appears, web UI request goes to the community `js_url`, update
  entity points at community manifest URL — a 404 from Pages is acceptable pre-launch;
  only the URLs matter).
- **Per script:** each `community/scripts/*.py` gets a `--self-test` mode with inline
  fixtures (mirroring upstream's convention), run in community-ci.
- **Per workflow:** validate via `workflow_dispatch` on a branch before relying on
  schedules; a deliberate sabotage branch (bad YAML in one device) must produce: red
  compile, `[broken]` issue, STATUS flip — then revert.
- **End-to-end (per release):** manual checklist item — Lachlan flashes one device from
  the live installer page.
- **Policy:** a test PR from a branch touching `common-anything` outside the allowlist
  (e.g. add `foo.txt` at repo root… note root files ARE allowed only if listed; use a
  disallowed path like `devices/guition-esp32-s3-4848s040/x`) must fail `policy`.
