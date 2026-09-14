# Runbook: upstream ref bumps

`community-ref-bump.yml` opens a PR whenever upstream tags a new release. Most
bumps are mechanical. This runbook covers the part that is not: **a green ref
bump does not mean the devices actually match upstream.**

## What a ref bump does and does not sync

`assemble.py` clones upstream at the pin and runs upstream's own generators
against our device folders. Those generators rewrite the content between the
`// BEGIN GENERATED …` / `// END GENERATED …` markers in
`devices/<slug>/device/sensors.yaml`, and `assemble.py` hard-fails if they
modify anything *outside* those markers.

That leaves a gap. The generator decides what to emit from each device's
catalog entry, so when upstream adds a behaviour behind a **catalog flag we do
not set**, it emits the old code for us, nothing outside the markers changes,
and every check passes. The device stays on the previous behaviour with no
signal at all.

This is not hypothetical:

- **v2.9.0** started emitting `grid_rebuild_all(...)` in `apply_button_grid`
  for devices carrying `firmware.display.refreshRebuildsSubpages`. All eight
  community devices enable rotation and none set the flag, so all eight kept
  `grid_refresh_layout(...)`, which relayouts existing widgets instead of
  recreating them — rotating a panel could leave secondary cards bound to a
  previous definition. The v2.9.0 bump reported success.
- **v2.9.0** also moved every upstream device to a `panel_config:` block in
  `device.yaml`, which a ref bump never touches beyond the pin substitution.

`check_wiring_parity.py` now catches the first class automatically. It cannot
catch everything, hence the manual step below.

## Procedure

1. **Let the bump PR run.** If `assemble` fails with
   `Generators modified community device files outside generated blocks`, that
   is the expected signal for a generator-shape change — review the printed
   diff, and if it is upstream's own restructuring, take the regenerated
   content from `.assembly/devices/<slug>/device/sensors.yaml`.

2. **Diff our devices against upstream's reference devices.** This is the step
   that catches flag-gated drift. For each chip family, compare the
   hand-authored regions — not just the generated blocks:

   ```bash
   python3 community/scripts/assemble.py --skip-web
   diff .assembly/devices/guition-esp32-s3-4848s040/device/sensors.yaml \
        devices/<our-s3-device>/device/sensors.yaml
   diff .assembly/devices/guition-esp32-p4-jc1060p470/device/sensors.yaml \
        devices/<our-p4-device>/device/sensors.yaml
   ```

   Differences in slot counts, grid dimensions and device-specific ids are
   expected. Differences in **which helper is called**, or a script that exists
   upstream and not here, are drift — find the catalog flag that gates it.

3. **Check `device.yaml` structure too.** `diff` the same pair of
   `device/device.yaml` files. A ref bump only rewrites the pin substitution
   there, so new upstream blocks (like `panel_config:`) never arrive on their
   own.

4. **Read upstream's release notes and its `scripts/check_device_profiles.py`.**
   Upstream encodes intent in its own tests — `test_rotation_refresh_rebuilds_subpages`
   is what established that rotation-capable devices must rebuild subpages.
   A new test there usually means a new expectation of every device.

5. **Run the checks.**

   ```bash
   python3 community/scripts/check_pin_consistency.py
   UPSTREAM_CLONE=.assembly python3 community/scripts/check_include_parity.py
   UPSTREAM_CLONE=.assembly python3 community/scripts/check_wiring_parity.py
   python3 community/scripts/check_generated_blocks.py
   python3 community/scripts/vendor_common.py --source .assembly --check
   ```

6. **Do not merge on a green compile alone.** Compiling proves the YAML is
   valid, not that the device behaves like upstream's. Steps 2–4 are the ones
   that catch silent divergence.

## When a catalog flag needs setting

Set it in `community/catalog-fragment.json` under the device's
`config.firmware.display`, then regenerate rather than hand-editing
`sensors.yaml` — the generator owns that file, and a hand edit is reverted on
the next assemble (and will fail the outside-generated-blocks check in the
meantime):

```bash
python3 community/scripts/assemble.py --skip-web   # errors, printing the diff
cp .assembly/devices/<slug>/device/sensors.yaml devices/<slug>/device/sensors.yaml
python3 community/scripts/assemble.py --skip-web   # now clean
python3 community/scripts/ui_stamp.py --write
python3 community/scripts/generate_docs.py
```

## Gotchas

- **`check_device_profiles.py` always fails** in this repo. It asserts
  upstream's hardcoded fixture matches the profile slug list, which cannot hold
  once community devices are in the catalog. `assemble.py` treats validators as
  non-fatal for this reason. Do not chase it.
- **A device slug that is a prefix of another** (`…-tab5` / `…-tab5-v1`) is
  handled in `assemble.py`'s overlay glob and in `DEVICES_POLICY.md`'s `allowed`
  patterns — use `builds/<slug>.*yaml`, never `builds/<slug>*.yaml`.
- **Regenerate `builds/` files before the final assemble run.** Creating them
  afterwards means the run never exercised them.
