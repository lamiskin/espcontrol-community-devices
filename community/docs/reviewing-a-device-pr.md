# Reviewing a Device PR

Checklist for triaging an incoming device submission (new device, or a
revision to an existing one). Companion to
[adding-a-device.md](adding-a-device.md), which is the contributor-facing
side of the same process.

## 1. Check CI first

All of these should be green before a deeper read is worth doing:

- **policy** — the PR's changed files match an `allowed` glob for every slug
  they touch, required files exist, nothing in `forbidden` was touched
- **assemble** — the catalog merges and generators run cleanly
- **compile** (per device) — every device in the matrix still compiles, not
  just the new one
- **builder-smoke** (per device) — the generated build manifests are valid

A red check here means don't bother with the rest of this list yet — send it
back first.

## 2. Cross-check the four files that must move together

A device PR touches four places that all need to agree, and CI's `policy`
check does not verify they're mutually consistent — only that each touched
file is *allowed*:

- **`community/devices.json`** — the new slug must be in the `"devices"`
  array. **This is the one most likely to be silently missing** — a PR can
  have a complete `catalog-fragment.json` entry, a full device directory, and
  still fail validation with "unknown font id" errors if this file wasn't
  updated, because `assemble.py` gates the device-folder overlay on this list
  specifically (see `adding-a-device.md` step 7 for the mechanism). If you
  see font-id errors on an otherwise-complete-looking PR, check this file
  before anything else.
- **`community/catalog-fragment.json`** — the device's profile, slot count,
  layout, and web-configurator dimensions
- **`community/STATUS.md`** — a row for the device
- **`community/DEVICES_POLICY.md`** — a policy block for the slug (allowed/
  required/forbidden globs)

If any one of these four is missing, CI's `policy` check can still pass
(it validates the files that *are* present, not that all four exist) — this
has to be checked by hand.

## 3. Chip-family policy

Per `DEVICES_POLICY.md`: ESP32-S3/P4 submissions are assessed on the config
alone. Anything else (ESP32, ESP32-C3, ESP8266) needs evidence in the PR of
real-world responsiveness, memory headroom, and multi-day stability — a
compile-only submission on a non-preferred chip should not be waved through
on CI passing alone.

For ESP32-P4 devices specifically, also confirm:

- `use_psram: true` is set on the `esp32_hosted:` block (the hosted-WiFi
  buffer-pool rule — CI's `check_esp32_hosted_psram.py` should already
  enforce this, but it's worth eyeballing given how easy it was for 8/8
  existing devices to miss the underlying flag historically)

## 4. OTA buffer override

Every device's `packages.yaml` needs a `# --- community hosting overrides
---` block setting `buffer_size_rx`/`buffer_size_tx: 4096` on `http_request:`.
CI's `check_ota_buffer.py` enforces this, but confirm the values are `4096`
and not some other number a contributor guessed at.

## 5. Hardware evidence vs claimed status

- **Working** claimed → photo or video of the device booting, touch working,
  and a card rendering must actually be attached to the PR, not just
  described in prose
- **Untested** claimed → compile success is sufficient, but the STATUS.md row
  must actually say Untested, not Working

Cross-check the STATUS.md row's status against what's actually attached —
don't take the PR checklist's checkmarks at face value.

## 6. Spot-check device.yaml against the stated hardware

You're very unlikely to have the hardware yourself, so this isn't a full
pin-by-pin audit — but do check for:

- Comments explaining *why* non-obvious `sdkconfig_options` are set (cache
  line sizes, PSRAM allocation, watchdog timeouts) — a submission with these
  unexplained is a sign the values were copied from another device without
  understanding whether they apply here, which is worth asking about even if
  it compiles fine
- Pins that plausibly match the product's published wiring/datasheet, where
  one is linked in the issue or PR
- Whether anything (audio, a sensor, a peripheral) was copied from a
  different device's config with pins swapped but not actually verified on
  this hardware — flag it explicitly rather than let it ride in silently as
  "supported"

## 7. Source attribution

`STATUS.md`'s Source column should link back to where the port came from —
an upstream espcontrol PR/issue, a linked personal fork, or another
community member's earlier attempt. Not policy-enforced, but a blank Source
column on a PR that clearly built on someone else's prior work (check the PR
description and any linked issues) is worth a comment asking for the
citation before merge.

## 8. Merge

Once the above holds: squash or merge per the contributor's commit structure,
credit every contributor via `Co-authored-by:` trailers if not already
present, and confirm the STATUS.md status matches what's actually going live.
