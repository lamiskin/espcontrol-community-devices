# Requirements Document

## Introduction

Build `espcontrol-community`: a standalone GitHub repository that hosts touchscreen
device configurations that the upstream project
[jtenniswood/espcontrol](https://github.com/jtenniswood/espcontrol) has declined to
officially support. The repo must not hand-duplicate upstream code, must track upstream
versions safely, must let end users install community devices with the same
browser-installer + ESPHome experience as official devices, and must accept community
pull requests for new hardware.

Background analysis and the architecture decision record live in
`/Users/lachlan/Kiro/espcontrol-community-plan.md` (Plan v2). This spec implements
"Option C" (thin overlay repo with pinned remote includes), gated by a feasibility spike
with a defined fallback ("Option B", composed dist branch).

The workspace folder containing this spec (`~/Kiro/espcontrol-community/`) becomes the
root of the new repository.

## Requirements

### Requirement 1: No duplicated upstream code

**User Story:** As the repo maintainer, I want community devices to reuse upstream's
shared config, components, and web UI source without copying them into this repo, so
that upstream improvements flow in without manual porting.

#### Acceptance Criteria

1. WHEN the repository is inspected THEN it SHALL contain only community-owned files: community device directories, build entry points, a catalog fragment, tooling, docs, and CI workflows — no copies of upstream `common/`, `components/`, or `src/` files.
2. WHEN a community device's YAML needs upstream shared config THEN it SHALL reference those files via ESPHome remote git packages pointed at the upstream repository at a pinned ref.
3. WHEN a community device compiles THEN the espcontrol external components SHALL be fetched from the upstream repository at the same pinned ref (via the existing `espcontrol_component_url` / `espcontrol_component_ref` substitutions).

### Requirement 2: Pinned upstream version, only green states exposed

**User Story:** As an end user, I want my panel's config to reference a tested upstream
version, so that upstream refactors never break my device unexpectedly.

#### Acceptance Criteria

1. WHEN any file in the repo references upstream THEN the ref SHALL come from the single source of truth `community/upstream-ref.txt` (a tag or commit SHA, never a branch name).
2. WHEN the pinned ref is changed THEN the change SHALL land only via a pull request in which every community device compiled successfully.
3. WHEN a scheduled ref-bump job finds a newer upstream release THEN it SHALL open a pull request (never push to main directly) containing the ref update and compile results.
4. IF a device fails to compile in a ref-bump PR THEN the PR SHALL NOT be merged and the failure SHALL be reported in the PR body.

### Requirement 3: End-user install experience

**User Story:** As an end user with a community-supported panel, I want to flash from a
web page and configure via the panel's web UI, just like an official device.

#### Acceptance Criteria

1. WHEN a user opens the community GitHub Pages installer THEN they SHALL be able to flash a factory image for each Working community device via ESP Web Tools.
2. WHEN a flashed device serves its web UI THEN `web_server.js_url` SHALL point at the community Pages `www.js` (built with community device profiles embedded), not upstream's.
3. WHEN a flashed device checks for firmware updates THEN the `update` component's `source` SHALL point at the community Pages `firmware/<slug>/manifest.json`.
4. WHEN a user's `esphome.yaml` uses the community remote package THEN a plain `esphome compile` on a machine with ESPHome 2026.6.5 SHALL succeed with no local checkout of upstream.

### Requirement 4: Contributor pull-request flow

**User Story:** As a hardware owner, I want to contribute a new device via a small,
well-validated PR, so that supporting my board doesn't require understanding the whole
project.

#### Acceptance Criteria

1. WHEN a PR is opened THEN CI SHALL verify the changed files touch only the paths allowed by `community/DEVICES_POLICY.md` for that device slug, and fail otherwise.
2. WHEN a PR adds or changes a device THEN CI SHALL compile that device's build entry point with ESPHome 2026.6.5.
3. WHEN a PR adds a device THEN CI SHALL verify the device's upstream include list matches the reference upstream device for its chip family (parity check), failing on unexplained differences.
4. WHEN a contributor opens the PR form THEN a template SHALL require: policy compliance confirmation, compile evidence, hardware-tested photo/video, catalog fragment entry, and STATUS row.

### Requirement 5: Continuous health visibility

**User Story:** As a user choosing a panel, I want to see which community devices
currently work, so I don't buy hardware that is broken.

#### Acceptance Criteria

1. WHEN the nightly workflow runs THEN it SHALL compile every device in `community/devices.json` at the current pin.
2. IF a device fails the nightly compile THEN the workflow SHALL open (or update, never duplicate) an issue titled `[broken] <slug>` and set that device's row in `community/STATUS.md` to Broken.
3. WHEN a previously broken device compiles again THEN its STATUS row SHALL be set back to Working.

### Requirement 6: Releases

**User Story:** As a maintainer, I want tagged releases that build all factory images and
publish installer/OTA manifests, so users get reproducible firmware.

#### Acceptance Criteria

1. WHEN a tag matching `community-v*` is pushed THEN CI SHALL compile every device's factory build, generate ESP Web Tools manifests and OTA update manifests, and attach binaries to a GitHub Release.
2. WHEN a release completes THEN GitHub Pages SHALL serve the updated installer page, `webserver/www.js`, and per-device `firmware/<slug>/manifest.json`.
3. WHEN a release is tagged THEN the tag name SHALL embed the upstream pin (format `community-vX.Y.Z+<upstream-ref>`).

### Requirement 7: Feasibility spike gates the architecture

**User Story:** As the maintainer, I want the risky mechanism (remote includes with
per-file vars and substitution scoping) proven before building everything on it.

#### Acceptance Criteria

1. WHEN implementation starts THEN the first completed work SHALL be a spike that converts upstream's `guition-esp32-s3-4848s040` device to remote-include form and compiles it.
2. IF the spike compile fails for a structural reason (substitutions not reaching remotely included files, per-file vars not applied, unfixable load-order breakage) THEN implementation SHALL switch to the Option B fallback described in the design document, and the spike verdict SHALL be recorded in `community/SPIKE.md`.
3. WHEN the spike passes THEN `community/SPIKE.md` SHALL record GO plus any syntax corrections discovered, and later tasks SHALL use the corrected syntax.

### Requirement 8: Seed devices

**User Story:** As the maintainer, I want the repo launched with the community devices
already contributed upstream as unmerged PRs, with their authors credited.

#### Acceptance Criteria

1. WHEN seeding completes THEN the repo SHALL contain, as merged devices or as parked `needs-rebase` draft PRs, ports of upstream PRs [#823](https://github.com/jtenniswood/espcontrol/pull/823), [#797](https://github.com/jtenniswood/espcontrol/pull/797), [#348](https://github.com/jtenniswood/espcontrol/pull/348), [#293](https://github.com/jtenniswood/espcontrol/pull/293), [#660](https://github.com/jtenniswood/espcontrol/pull/660), [#359](https://github.com/jtenniswood/espcontrol/pull/359), [#351](https://github.com/jtenniswood/espcontrol/pull/351), [#885](https://github.com/jtenniswood/espcontrol/pull/885).
2. WHEN a seed device is committed THEN the commit SHALL include `Co-authored-by:` for the original PR author and link the source PR.
3. IF a seed device does not compile against the current pin THEN it SHALL be parked as a draft PR labeled `needs-rebase` with STATUS Broken, not merged.

### Requirement 9: Licensing, attribution, and non-official status

**User Story:** As the upstream maintainer (third party), I want the community repo to
respect the upstream license and never present itself as official.

#### Acceptance Criteria

1. WHEN the repo is created THEN it SHALL carry upstream's LICENSE verbatim and a NOTICE identifying it as an unofficial community derivative of jtenniswood/espcontrol.
2. WHEN the README or installer page is rendered THEN it SHALL state the unofficial status and link to the upstream project.
3. WHEN any outward-facing action is needed (posting to upstream's tracker/discussions, making the repo public) THEN the implementer SHALL stop and ask Lachlan first.

### Requirement 10: Human decision gates

**User Story:** As the repo owner, I want the implementing agent to stop at defined
points rather than guess.

#### Acceptance Criteria

1. WHEN the spike verdict is reached (GO or NO-GO) THEN the implementer SHALL report it and wait for approval before Phase 1.
2. WHEN hardware flashing is required (spike runtime test, release verification) THEN the implementer SHALL hand off to Lachlan with exact instructions rather than attempt it.
3. WHEN secrets, PATs, or GitHub settings changes are needed THEN the implementer SHALL list exactly what is needed and wait.
