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
| ESPHome version pin (read from `.github/esphome.env` at the pinned ref) | `.github/esphome.env` |
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

#### `community/DEVICES_POLICY.md` format (machine-parseable)

The policy file uses a fenced YAML block per device slug plus a `_global` entry for
repo-wide allowed paths. `check_policy.py` parses these blocks as the enforcement source:

```yaml
# --- begin policy ---
_global:
  allowed:
    - community/**
    - README.md
    - .github/**
    - LICENSE
    - NOTICE

# Example device block. The slug comes from the ported PR's actual device
# directory name (e.g. PR #823's dir under devices/) — never invent one.
<slug-from-ported-pr>:
  allowed:
    - devices/<slug-from-ported-pr>/**
    - builds/<slug-from-ported-pr>*.yaml
  required:
    - devices/<slug-from-ported-pr>/esphome.yaml
    - devices/<slug-from-ported-pr>/packages.yaml
    - devices/<slug-from-ported-pr>/device/device.yaml
  forbidden:
    - common/**
    - components/**
    - src/**
# --- end policy ---
```

Rules: a PR's changed files must each match at least one `allowed` glob from either `_global`
or the device slug(s) touched. If a PR adds a new device, it must also add that slug's
policy block in the same PR. `required` files must exist in the HEAD tree for any PR that
touches that slug. `forbidden` paths cause an unconditional failure if touched.

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

### 6b. `community/scripts/bump_refs.py`

`python3 community/scripts/bump_refs.py <new-ref>`

Rewrites every `ref:` value in remote-package blocks and every `espcontrol_component_ref:`
value in `devices/**/*.yaml` to `<new-ref>`. Also updates `community/upstream-ref.txt`.
Algorithm:

1. Read `<new-ref>` from argv (validate: must be a tag like `vX.Y.Z` or a 40-char SHA).
2. For each `.yaml` file under `devices/`: regex-replace lines matching
   `^(\s+ref:\s+).*$` within a block that has `url:.*jtenniswood/espcontrol` → set value
   to `<new-ref>`. Also replace `espcontrol_component_ref: "..."` → `espcontrol_component_ref: "<new-ref>"`.
3. Write `<new-ref>` to `community/upstream-ref.txt`.
4. Run `check_pin_consistency.py` as a post-condition (exit nonzero if any mismatch remains).
5. Print summary: `Updated N files, pin is now <new-ref>`.

Idempotent: running with the current pin is a no-op.

### 7. GitHub Actions workflows

All jobs: `runs-on: ubuntu-latest`. Install ESPHome with
`pip install esphome==$(grep ESPHOME_VERSION .assembly/.github/esphome.env | cut -d= -f2)` (always read from `.assembly/.github/esphome.env` after assembly — never hardcode a version). Cache: `actions/cache`
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
  Post-matrix job: for failures,
  `gh issue list --state open --search '"[broken] <slug>" in:title'` (keep the inner
  quotes — the bracketed phrase must be one search term)
  → if no match, create; if match, comment (deduplication by exact title match); set the
  STATUS.md row to Broken (recording its previous status in the row's notes or the
  issue body). On recovery, restore the device's PRE-broken status — Working only if it
  was hardware-verified before breaking, otherwise Untested (compile success alone never
  sets Working) — and close the matching `[broken] <slug>` issue (`gh issue close` by
  exact title match). Commit STATUS changes with message `chore: nightly status update`.
- **community-ref-bump.yml** — `on: schedule: "0 4 * * 1"` + dispatch. Query latest
  upstream release: `gh api repos/jtenniswood/espcontrol/releases/latest --jq .tag_name`.
  If newer than `<PIN>`: branch `ref-bump/<tag>`, write `upstream-ref.txt`, run
  `python3 community/scripts/bump_refs.py` (small script: rewrite every `ref:`/
  `espcontrol_component_ref:` in `devices/**` to the new pin — reuse
  check_pin_consistency's discovery), run assemble + parity for drift report, compile
  all devices, open a PR (label `ref-bump`) whose body contains per-device compile
  results and the parity report. Never auto-merge.
  **Tag format note (Req 6 AC3):** The `community-vX.Y.Z+<upstream-ref>` format uses
  semver build metadata (`+`). The trigger glob `"community-v*"` should match it (`*`
  matches any suffix including `+`), but this is UNVERIFIED until the task-13 test tag —
  confirm there, and record the outcome in `community/SPIKE.md`. If `+` causes trouble
  anywhere (Actions trigger, artifact naming, registries), fall back to
  `community-vX.Y.Z-upstream.<ref>`; the `"community-v*"` glob covers both formats.

- **community-release.yml** — `on: push: tags: ["community-v*"]`. Assemble; for each
  device: `esphome compile builds/<slug>.factory.yaml`; collect
  `.assembly/.esphome/build/**/firmware.factory.bin` and `firmware.ota.bin` (verify
  exact artifact names/paths from upstream's `release.yml` and
  `scripts/check_firmware_release.py` at the pin — mirror upstream's manifest JSON
  shapes for both ESP Web Tools and the OTA `update:` component); write
  `community-pages/firmware/<slug>/manifest.json`; `gh release create` with binaries.
- **community-pages.yml** — `on: workflow_run` after release, + dispatch. Publish
  `community-pages/` via `actions/upload-pages-artifact` + `actions/deploy-pages`:
  `index.html` (installer: one `<esp-web-tools-install-button>` per device, esp-web-tools
  loaded from unpkg CDN), `webserver/www.js`, `firmware/<slug>/manifest.json`.
  **Installer listing rule:** Working and Untested devices are BOTH listed — Untested
  ones with a visible "not yet hardware-verified" badge. Only Broken devices are
  omitted. (Untested must be flashable, otherwise the first hardware verification could
  never happen from the installer page — see task 14.)

#### Rollback procedure (Req 6 AC4)

To revert a broken release: tag a new patch version (e.g. `community-v1.0.1+<prev-good-ref>`)
pointing `community/upstream-ref.txt` at the previous known-good upstream ref. The existing
`community-release.yml` triggers on the new tag, recompiles all devices at the reverted pin,
and `community-pages.yml` overwrites the Pages-served manifests, installer, and `www.js` on
deploy. No special rollback workflow is needed — the normal release pipeline handles it because
it always publishes to the same Pages paths (not versioned subdirectories). OTA-connected
devices will see the reverted manifest on their next update check.

### 8. Seed device porting (Req 8)

Seed devices are upstream PRs that were never merged. Porting process:

1. **Extract**: For each seed PR, fetch the PR's branch files:
   `gh pr diff <number> --repo jtenniswood/espcontrol > /tmp/pr-<number>.patch`
   or clone the PR author's fork at the PR branch. Extract the device directory
   (`devices/<slug>/`) and build files (`builds/<slug>*.yaml`).

2. **Convert**: Run `python3 community/scripts/convert_packages.py devices/<slug>/packages.yaml`
   to transform relative includes into remote-include form. Verify the output matches
   the pattern in Section 1 (correct split points, vars, overrides).

3. **Catalog**: Add the device entry to `community/catalog-fragment.json` by copying the
   closest official device's entry from upstream's `devices/catalog.json` at `<PIN>` and
   editing slug/name/screenSize/resolution/platform fields.

4. **Register**: Add the slug to `community/devices.json` and a row to `community/STATUS.md`
   (status: Untested).

5. **Compile test**: Run `python3 community/scripts/assemble.py && cd .assembly && esphome compile builds/<slug>.yaml`.

6. **Commit**: If compile passes, commit with:
   - `Co-authored-by: Original Author <email>` (from the PR or git log)
   - Commit message body: `Ported from jtenniswood/espcontrol#<number>`
   - Set STATUS to **Untested**, merge to main. A compile pass never means Working:
     Working is set only after hardware verification (task 14 / `hardware-tested`).

7. **Park if broken**: If compile fails and the fix is non-trivial (not a typo or missing
   var), create a draft PR from a branch `seed/<slug>`, label it `needs-rebase`, set STATUS
   to Broken. The commit still carries `Co-authored-by`.

8. **Credit**: The PR description (or commit for direct merges) links the source PR URL.
   The `Co-authored-by` trailer ensures GitHub attributes the contribution.

#### Seed device list

Device names below are from the actual upstream PR titles (2026-07-19). Chip family
marked "verify" must be confirmed from the PR's own `device/device.yaml` (`esp32:`
platform block) before porting — do NOT trust this table over the PR's files. The PR
number is authoritative; if a name disagrees, re-check with
`gh pr view <N> --repo jtenniswood/espcontrol`.

| PR | Device (from PR title) | Chip family | Reference device |
|---|---|---|---|
| #823 | Guition JC3248W535 3.5" ESP32-S3 | esp32-s3 | guition-esp32-s3-4848s040 |
| #797 | Waveshare ESP32-S3-Touch-LCD-4 | esp32-s3 | guition-esp32-s3-4848s040 |
| #348 | Lilygo JC3248W535 | verify (likely esp32-s3) | per chip family |
| #293 | Waveshare ESP32-S3 Smart 86 Box | esp32-s3 | guition-esp32-s3-4848s040 |
| #660 | Tuya T3E 4" | verify | per chip family |
| #359 | Elecrow CrowPanel Advance 5" | verify (likely esp32-s3) | per chip family |
| #351 | SenseCAP Indicator D1 | verify (likely esp32-s3) | per chip family |
| #885 | Seeed reTerminal D1001 8" ESP32-P4 | esp32-p4 | guition-esp32-p4-jc1060p470 |

### 9. Option B fallback (only if the spike fails — see requirements 7)

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
  config on the ESPHome version from `.assembly/.github/esphome.env` → hardware flash by Lachlan (verify: boots to loading
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
- **Rollback (Req 6 AC4):** after a successful release, tag a new patch release reverting
  `upstream-ref.txt` to the prior pin. Verify: release workflow triggers, compiles succeed,
  Pages deploy overwrites manifests with the older firmware, and the installer page serves
  the reverted binaries.
- **Seed devices (Req 8):** for at least one seed device, verify: `Co-authored-by` appears
  in the commit, the source PR is linked, and the device compiles. For a deliberately broken
  seed (wrong pin or missing upstream file), verify it lands as a draft PR with `needs-rebase`
  label and Broken status.
