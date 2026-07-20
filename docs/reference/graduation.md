---
title: Device Graduation
description: "What happens when the upstream EspControl project adopts a community device: the OTA handover plan."
---

<!--@include: ../parts/warning.md-->

# Device Graduation

If the upstream EspControl maintainer decides to officially support a device
that started here, that device **graduates**: upstream becomes its home, and
this project's job is to hand existing panels over cleanly — without anyone
reflashing over USB.

## What users experience

Nothing, ideally. Your panel offers a normal OTA update; after installing it,
the panel is running official upstream firmware and all future updates come
from upstream's channel. The panel's configuration is preserved (EspControl
backups also exist as a safety net).

## The handover mechanics

Community panels poll this project's update feed at
`firmware/<device>/manifest.json`. Graduation uses that feed to redirect them:

1. **Upstream adopts the device** — its config lands in the upstream repo and
   ships in an upstream release with upstream-hosted firmware and update
   manifests.
2. **This project publishes a handover manifest** at the device's existing
   feed path. It advertises upstream's official build (version and binary
   URLs point at upstream's hosting), so the panel's next update check offers
   the official firmware.
3. **Panels install the handover update.** The installed firmware is
   upstream's build, whose update source points at upstream's feed — from this
   moment the panel updates from upstream and never contacts this project
   again.
4. **The handover manifest stays published for at least 12 months** so
   rarely-powered panels still catch the transition. The device's page here is
   replaced with a pointer to upstream's documentation.

In the [status table](https://github.com/lamiskin/espcontrol-community-devices/blob/main/community/STATUS.md)
the device is marked **Graduated**; its config is removed from this repo
(upstream's copy is now canonical), and the installer stops offering it —
new installs come from
[upstream's installer](https://jtenniswood.github.io/espcontrol/getting-started/install).

## Edge cases

- **Slug differences**: if upstream adopts the device under a different
  internal name, the handover manifest still lives at the *old* community
  path — panels don't care what the device is called upstream.
- **Panels that miss the window**: a panel powered on after the handover
  manifest is retired can always be moved manually — flash upstream's
  firmware once from the
  [upstream installer](https://jtenniswood.github.io/espcontrol/getting-started/install);
  configuration can be restored from an EspControl backup.
- **Partial adoption**: if upstream adopts the hardware but with meaningful
  config differences, the handover release notes will call out anything that
  needs attention before updating.

## Candidates

The most likely first graduation is the **Seeed reTerminal D1001** — its
touch driver already lives in an upstream pull request. When that merges and
ships in an upstream release, this process gets its first real run.
