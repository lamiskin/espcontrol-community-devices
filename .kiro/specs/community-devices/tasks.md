# Implementation Plan

Rules for the implementer, read first:

- Work through tasks in order. Do not start a task until the previous one's
  verification command passes.
- `<PIN>`: latest upstream release tag of jtenniswood/espcontrol at start time
  (`gh api repos/jtenniswood/espcontrol/releases/latest --jq .tag_name`); `<ORG>`:
  ask Lachlan (github.com account is `lamiskin`; if `gh` targets the wrong host, add `--hostname github.com` or
  `GH_HOST=github.com`).
- A reference clone of upstream already exists at `/Users/lachlan/Kiro/espcontrol`.
  Read files there freely; NEVER modify or commit in that clone.
- The design document's snippets are normative — copy them, don't reinvent. When the
  design says "verify X at the pin", actually open the file and check.
- STOP AND ASK LACHLAN at every task marked ⛔GATE. Do not proceed past a gate without
  an explicit go-ahead.

- [ ] 1. Spike: prove remote-include form compiles (Option C go/no-go)
  - Create scratch dir `spike/` inside this workspace (do not git-init yet).
  - Copy `devices/guition-esp32-s3-4848s040/` from the upstream clone at tag `<PIN>`
    (`git -C /Users/lachlan/Kiro/espcontrol fetch --tags && git -C /Users/lachlan/Kiro/espcontrol show <PIN>:...` or checkout a temp worktree) into `spike/devices/spike-4848s040/`.
  - Rewrite `spike/devices/spike-4848s040/packages.yaml` into remote-include form
    exactly per the design doc pattern (design §Components 1), with `<PIN>` and
    placeholder `<PAGES>` = `https://example.invalid` for now.
  - In `device/device.yaml` set `espcontrol_component_ref: "<PIN>"`.
  - Write `spike/user.yaml`: copy the shape of upstream `devices/guition-esp32-s3-4848s040/esphome.yaml` but replace the remote package with a LOCAL include: `packages: setup: !include devices/spike-4848s040/packages.yaml`, plus hardcoded test wifi `ssid: "ESPControl"` / `password: "espcontrol"` (no secrets.yaml).
  - `python3 -m venv .venv && .venv/bin/pip install esphome==$(git -C /Users/lachlan/Kiro/espcontrol show <PIN>:.github/esphome.env | grep ESPHOME_VERSION | cut -d= -f2)` (read the version AT THE PIN via `git show`, not from the clone's working tree — the working tree tracks main and may have a newer version than the pinned tag).
  - Verify: `.venv/bin/esphome compile spike/user.yaml` succeeds. Debug loop guidance: config-stage errors about unknown substitutions or duplicate ids map to the Error Handling table in the design doc — check the table BEFORE improvising. Full compile takes 30+ min; `esphome config spike/user.yaml` first for fast iteration.
  - Write `community/SPIKE.md` (create dirs): GO or NO-GO, every syntax correction discovered, the actual www.js bundle path noted for later.
  - _Requirements: 7.1, 7.2, 7.3_

- [ ] 2. ⛔GATE Report spike verdict to Lachlan
  - Report GO/NO-GO and SPIKE.md contents. If NO-GO: all later tasks switch to Option B per design §Components 9 "Option B fallback" (task deltas: skip convert_packages.py usage; add community-dist.yml; device packages.yaml keeps relative includes + overrides).
  - Offer Lachlan the optional hardware flash check now (design §Testing Strategy spike bullet); proceed without it if he defers.
  - _Requirements: 10.1, 10.2_

- [ ] 3. Initialize the repository skeleton
  - In THIS workspace root (`~/Kiro/espcontrol-community-devices/` — the folder containing `.kiro/`): `git init -b main`.
  - Create the full layout from design §Architecture: `community/upstream-ref.txt` (containing `<PIN>`), `community/devices.json` (`{"devices": []}`), `community/catalog-fragment.json` (`{"devices": {}}`), `community/STATUS.md` (header row only), `community/DEVICES_POLICY.md` (machine-parseable YAML-block format per design §DEVICES_POLICY.md format: `_global` entry with repo-wide allowed paths, plus per-slug blocks with `allowed`/`required`/`forbidden` globs; include ESP32-S3/P4 class restriction and hardware evidence note in prose above the YAML block), `.gitignore` (`.assembly/`, `.venv/`, `spike/`, `community-pages/webserver/www.js`).
  - `LICENSE`: copy upstream's verbatim. `NOTICE`: copy upstream's, append unofficial-derivative line. `README.md`: unofficial status + upstream link + STATUS link + install pointer (Pages URL placeholder).
  - Move `community/SPIKE.md` from task 1 in; keep `spike/` uncommitted.
  - Verify: `git status` clean after commit; every path in design layout exists.
  - _Requirements: 1.1, 9.1, 9.2_

- [ ] 4. ⛔GATE Create the GitHub repo
  - Confirm with Lachlan: final name (`espcontrol-community`?), owner org/user, public vs private-first.
  - `gh repo create <ORG>/espcontrol-community --public --description "Community-maintained device configs for EspControl (unofficial)" && git remote add origin ... && git push -u origin main`
  - Enable Issues; Pages source = GitHub Actions (`gh api -X POST repos/<ORG>/<REPO>/pages -f build_type=workflow` — if it errors, ask Lachlan to enable in Settings→Pages).
  - Create labels: `gh label create` for `device-request`, `needs-rebase`, `broken`, `hardware-tested`, `sync-broken`, `ref-bump`.
  - _Requirements: 9.3, 10.3_

- [ ] 5. Implement community/scripts/convert_packages.py
  - Per design §Components 2 (line-based transform; idempotent; reads pin from `community/upstream-ref.txt`; appends overrides using `<PAGES>` = real Pages URL `https://<ORG>.github.io/espcontrol-community`).
  - Include `--self-test`: embed the upstream 4848s040 packages.yaml include-block as a fixture string, convert, assert the output contains `upstream_a:`, 9 vars entries, correct interleave order, and both override blocks.
  - Verify: `python3 community/scripts/convert_packages.py --self-test` passes; running it on the task-1 spike output is a no-op.
  - _Requirements: 1.2_

- [ ] 6. Implement community/scripts/assemble.py
  - Per design §Components 3, steps 1–6 (defer step 7 web bundle to task 8). Add `--sync-generated` per design. `.assembly/` must be gitignored already.
  - First run will reveal the catalog.json device-collection structure — read `.assembly/devices/catalog.json`, implement the merge against the REAL structure, and document it in a comment.
  - Include `--self-test` with a tiny fixture catalog + fragment.
  - Verify (with still-empty devices.json): `python3 community/scripts/assemble.py` clones upstream at `<PIN>`, runs generators + checks green, exits 0.
  - _Requirements: 1.1, 2.1_

- [ ] 7. Implement the check scripts
  - `check_policy.py`, `check_include_parity.py`, `check_pin_consistency.py` per design §Components 4–6, each with `--self-test`.
  - Verify: all three `--self-test`s pass; `check_pin_consistency.py` passes on the repo; `check_policy.py --base HEAD~1 --head HEAD` behaves sanely.
  - _Requirements: 4.1, 4.3, 2.1_

- [ ] 8. Web bundle build in assemble.py
  - Implement design §Components 3 step 7 (`npm ci`, `python3 scripts/build.py www`, locate output bundle — the path recorded in SPIKE.md if found during spike; otherwise find what `build.py www` wrote under `docs/public/webserver/` and record it now), copy to `community-pages/webserver/www.js`.
  - Verify: run with empty devices.json → bundle produced; grep for an OFFICIAL slug (e.g. `guition-esp32-s3-4848s040`) succeeds (community slug grep becomes meaningful in task 10).
  - _Requirements: 3.2_

- [ ] 9. First device port: Guition JC3248W535 3.5" ESP32-S3 (upstream PR #823)
  - `git -C /Users/lachlan/Kiro/espcontrol fetch origin pull/823/head:pr-823` and copy its `devices/<slug>/` + `builds/<slug>*.yaml` into this repo (keep upstream's slug).
  - Reconcile against the S3 reference at `<PIN>`: diff the PR's packages.yaml substitutions/includes vs current `devices/guition-esp32-s3-4848s040/packages.yaml`; add anything upstream added since the PR was written (this is the expected-hard part — every unexplained missing substitution will surface as a compile error naming it).
  - Run `convert_packages.py` on it. Set `espcontrol_component_ref: "<PIN>"`. Point `esphome.yaml`'s remote package and `builds/<slug>.factory.yaml`'s `dashboard_import` at `<ORG>/espcontrol-community` per design §Components 1 notes.
  - Author its `community/catalog-fragment.json` entry (copy 4848s040's catalog entry from `.assembly/devices/catalog.json`, adapt resolution/layout per the PR's original manifest/catalog changes). Add slug to `devices.json`; STATUS row Untested.
  - Run `assemble.py --sync-generated` to populate generated blocks; then `check_include_parity.py`.
  - Verify: `cd .assembly && ../.venv/bin/esphome compile builds/<slug>.yaml` succeeds; www.js grep for the community slug succeeds. Also run `python3 community/scripts/check_pin_consistency.py` against the repo now that a real device exists — confirms the script works with actual device files.
  - Commit with `Co-authored-by:` crediting the PR author (get login: `gh pr view 823 --repo jtenniswood/espcontrol --json author`; format `Co-authored-by: <login> <<login>@users.noreply.github.com>`), PR link in the message body.
  - _Requirements: 1.2, 1.3, 8.1, 8.2, 3.4_

- [ ] 10. CI workflow: community-ci.yml
  - Per design §Components 7. Matrix compile only PR-touched devices. Self-tests of all community scripts run in the `policy` job.
  - Verify by opening two test PRs from branches: (a) one modifying `devices/guition-jc3248w535…/device/lvgl.yaml` trivially → policy green, compile runs; (b) one adding a file at `devices/guition-esp32-s3-4848s040/x.txt` (an official slug not in devices.json) → policy red. Close both.
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 11. Nightly workflow: community-nightly.yml
  - Per design §Components 7: matrix all slugs, `[broken] <slug>` issue create-or-comment (search first, never duplicate), STATUS.md flip commits.
  - Verify: `gh workflow run community-nightly.yml` → green. Sabotage test on a branch via dispatch input `ref:` (add `workflow_dispatch: inputs: ref` and checkout that ref): broken YAML → issue filed + STATUS flip; then revert and confirm Working restored and the `[broken] <slug>` issue is closed (not just commented — per Req 5 AC3 it SHALL be closed).
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 12. Ref-bump workflow: community-ref-bump.yml + bump_refs.py
  - Per design §Components 7. Implement `bump_refs.py` per design §6b (regex rewrite of `ref:` and `espcontrol_component_ref:` in `devices/**/*.yaml` + update `upstream-ref.txt`; post-condition: `check_pin_consistency.py` green). Include `--self-test`: fixture a small YAML with old ref, run, assert new ref in output and pin file updated.
  - Verify: temporarily set `upstream-ref.txt` to the PREVIOUS upstream release on a branch, dispatch the workflow against it → it must open a correctly-formed PR to that branch with compile results and parity report. Close the PR, delete branch.
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [ ] 13. Release + Pages workflows
  - `community-release.yml` and `community-pages.yml` per design §Components 7. Before writing manifest code, READ upstream's `.github/workflows/release.yml` and `scripts/check_firmware_release.py` at `<PIN>` in `.assembly/` and mirror the exact ESP Web Tools manifest shape and OTA manifest shape (chip family field, ota bin, md5 — whatever upstream emits).
  - Installer `community-pages/index.html`: unofficial banner, upstream credit link, per-device install buttons (esp-web-tools from unpkg). The release workflow SHALL parse `community/STATUS.md` at build time: Working AND Untested devices both get `<esp-web-tools-install-button>` elements (Untested with a visible "not yet hardware-verified" badge next to the button); only Broken devices are omitted. (Untested must be flashable or task 14's first hardware verification from the installer page is impossible.)
  - Verify: push tag `community-v0.0.1+<PIN>` → Release with factory binary + manifests; Pages live: installer page renders, `webserver/www.js` and `firmware/<slug>/manifest.json` URLs return 200. If the `+` in the tag fails to trigger the workflow, switch to `-upstream.<ref>` format per design §Tag format note and update the workflow trigger pattern.
  - Rollback verification (Req 6 AC4): after the successful release, push a second tag `community-v0.0.2+<PIN>` (same pin — simulating a "revert to known-good"). Confirm the release workflow fires, Pages artifacts are overwritten, and manifest URLs still return 200.
  - _Requirements: 6.1, 6.2, 6.3, 3.1, 3.2, 3.3_

- [ ] 14. ⛔GATE End-to-end hardware verification
  - Hand Lachlan: the installer page URL and the checklist — flash via browser, panel boots to loading screen then WiFi setup, web UI loads (from community js_url), update entity shows community manifest source, add to Home Assistant. Wait for results; fix what fails.
  - On success: STATUS row → Working with the release tag; mark the release as latest.
  - _Requirements: 10.2, 3.1, 3.2, 3.3_

- [ ] 15. Contributor experience
  - `community/docs/adding-a-device.md`: walkthrough distilled from task 9 (copy closest device dir; each `device/` file's role — link upstream `dev-docs/devices-and-builds.md`; catalog-fragment authoring; convert_packages.py; parity exceptions; local compile via assemble.py; hardware evidence requirement).
  - `.github/PULL_REQUEST_TEMPLATE.md` + `.github/ISSUE_TEMPLATE/device-request.yml` per requirements 4.4 (device request form: name, chip [S3/P4 only — link upstream rejections [#283](https://github.com/jtenniswood/espcontrol/issues/283)/[#90](https://github.com/jtenniswood/espcontrol/issues/90)], resolution, product link, "do you own it / can you test?").
  - Verify: new-issue and new-PR pages on GitHub render the forms.
  - _Requirements: 4.4_

- [ ] 16. Seed remaining devices (one PR each, in order)
  - Repeat the task-9 recipe for upstream PRs #797 (Waveshare ESP32-S3-Touch-LCD-4), #293 (Waveshare ESP32-S3 Smart 86 Box) — both confirmed S3 — then #348 (Lilygo JC3248W535), #660 (Tuya T3E 4"), #359 (Elecrow CrowPanel Advance 5"), #351 (SenseCAP Indicator D1), then #885 (Seeed reTerminal D1001, ESP32-P4) last. BEFORE porting each, determine the chip family from the PR's own `device/device.yaml` (`esp32:` platform block) — the design-doc table marks several as unverified; a wrong reference device produces confusing compile errors, so check first, and order any discovered P4 devices after the S3 ones. For P4 devices the reference is `guition-esp32-p4-jc1060p470` and includes/substitutions differ significantly; derive the conversion from that device's packages.yaml at `<PIN>`, including any extra files like network-coprocessor YAML. NOTE: the first P4 port is a mini-spike — if the remote-include split points differ structurally from S3, record amendments in `community/SPIKE.md`.
  - Non-compiling after a reasonable effort (~half day each): park as draft PR labeled `needs-rebase`, STATUS Broken, move on.
  - Verify per device: CI green, nightly includes it, installer lists it (after next release tag).
  - _Requirements: 8.1, 8.2, 8.3_

- [ ] 17. ⛔GATE Announce
  - Draft (do not post) a message for the upstream Discussion that followed issue #839: what the repo is, unofficial status, credit to upstream and to the seed-PR authors, invitation to contribute. Give the draft to Lachlan; he decides whether/where to post.
  - _Requirements: 9.3, 10.3_
