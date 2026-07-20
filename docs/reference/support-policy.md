---
title: Support Policy
description: "Where to report issues with community EspControl devices, what support to expect, and how hardware verification works."
---

<!--@include: ../parts/warning.md-->

# Support Policy

## Where to report issues

**All** issues encountered on a community device — crashes, display glitches,
touch problems, failed updates, *and* things that look like general EspControl
bugs — go to the
[community issue tracker](https://github.com/lamiskin/espcontrol-community-devices/issues).

**Never report issues from a community device to the upstream EspControl
repo.** Even a bug that seems unrelated to the hardware may be caused by the
community port, the pinned version, or the device itself — triage happens
here, and only a maintainer should escalate something upstream after
reproducing it on official hardware.

## What to expect

- The upstream EspControl project holds **no responsibility** for these
  builds — no support, no updates, no warranty of any kind.
- This is volunteer-maintained. Response times vary; fixes for
  device-specific problems depend on someone with that hardware being able to
  reproduce them.
- Community builds can be **buggier than official hardware**. Most devices
  here were contributed once and are compile-tested nightly, but only devices
  marked **Working** have been verified on a real panel.

## Device status meanings

| Status | Meaning |
|---|---|
| **Working** | Compiles at the current pin **and** hardware-verified with photo/video evidence |
| **Untested** | Compiles and is flashable; awaiting verification on real hardware |
| **Broken** | Fails to compile at the current pin; pulled from the installer until fixed |
| **Parked** | Not currently in the repo — waiting on an upstream dependency or a re-submission |
| **Graduated** | Adopted by upstream; updates handed over — see [Device Graduation](/reference/graduation) |

## Hardware verification

Owning a panel marked **Untested** makes you the most valuable contributor
this project can have:

1. Flash it from the [installer](/getting-started/install).
2. Confirm the basics: boots to the home screen, touch works, at least one
   card renders and controls its entity.
3. Open an issue (or comment on the device's port PR) with a photo or short
   video of the panel running.

That's it — the device flips to **Working** and every future user knows it's
solid.

## Security and stability expectations

Community firmware is built in public CI from the pinned upstream source plus
the device configs in this repo — no third-party binaries beyond what upstream
itself uses. That said, these builds don't go through the upstream
maintainer's hardware testing. If you need maximum reliability, buy an
[officially supported panel](https://jtenniswood.github.io/espcontrol/) and
use upstream firmware.
