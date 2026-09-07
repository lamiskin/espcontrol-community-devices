#!/usr/bin/env bash
# Publish — or finish publishing — the GitHub release for a tag.
#
# `gh release create` fails outright when a release already exists for the
# tag, which made the bare call this replaces fail in two situations:
#
#   1. The tag was made through GitHub's web UI. "Draft a new release" is the
#      only page there that can create a tag, and it creates the release at
#      the same moment. The push then triggers this workflow, which spends a
#      full device matrix build and fails on its very last step — leaving a
#      release with no binaries attached to it.
#   2. A retried create. If a create reached GitHub but its asset upload was
#      cut off mid-flight, the release existed from then on, so every later
#      attempt inside `retry` hit "release already exists" and could do
#      nothing but repeat the same failure.
#
# Both are the same shape: the release may or may not exist yet, and the job
# is to finish with it present, published, and carrying every asset. So the
# choice is made per attempt rather than once up front, which makes the whole
# operation idempotent and therefore safe to wrap in `retry`.
#
# Usage:
#   .github/scripts/publish_release.sh <tag> <title> <notes-file> \
#       <prerelease:true|false> [asset ...]
#
# Requires GH_TOKEN in the environment, like any other `gh` call in CI.

set -uo pipefail

# Resolve alongside this script so the workflow can call it from any cwd.
_PUBLISH_RELEASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

publish_release() {
  local tag="$1" title="$2" notes_file="$3" prerelease="$4"
  shift 4

  if gh release view "$tag" >/dev/null 2>&1; then
    echo "publish_release: release $tag already exists — updating in place" >&2
    # --draft=false publishes a release the UI route left as a draft; on an
    # already-published release it is a no-op. --prerelease is passed as an
    # explicit true/false so that re-running can also *clear* the flag, which
    # bare `--prerelease` cannot express.
    gh release edit "$tag" \
      --title "$title" \
      --notes-file "$notes_file" \
      --prerelease="$prerelease" \
      --draft=false || return $?

    # `gh release upload` with no files is an error, and a release with no
    # assets is a legitimate (if unusual) outcome.
    if [ "$#" -eq 0 ]; then
      return 0
    fi
    gh release upload "$tag" "$@" --clobber || return $?
    return 0
  fi

  local create_args=(--title "$title" --notes-file "$notes_file")
  if [ "$prerelease" = "true" ]; then
    create_args+=(--prerelease)
  fi
  gh release create "$tag" "$@" "${create_args[@]}"
}

# ---------------------------------------------------------------------------
# Self-test (`--self-test`). Stubs `gh` with a shell function — a function
# beats PATH lookup, so publish_release calls the stub without knowing — and
# asserts on the argv it would have sent.
# ---------------------------------------------------------------------------
_publish_release_self_test() {
  set -u
  local failures=0
  local gh_log exists create_effect

  gh() {
    gh_log="${gh_log}${*}"$'\n'
    case "${2:-}" in
      view)
        [ "$exists" = "true" ] && return 0
        return 1
        ;;
      create)
        # "half-done" reproduces the real retry trap: the release lands on
        # GitHub, then the asset upload dies, so the create reports failure
        # while the release now exists.
        if [ "$create_effect" = "half-done" ]; then
          exists=true
          return 1
        fi
        return 0
        ;;
    esac
    return 0
  }

  local notes
  notes=$(mktemp)
  echo "notes" > "$notes"

  _check_has() {
    if printf '%s' "$gh_log" | grep -qF -- "$2"; then
      echo "  ok: $1"
    else
      echo "  FAIL: $1 (expected to see '$2' in:" >&2
      printf '%s' "$gh_log" >&2
      echo "  )" >&2
      failures=$((failures + 1))
    fi
  }
  _check_lacks() {
    if printf '%s' "$gh_log" | grep -qF -- "$2"; then
      echo "  FAIL: $1 (did not expect '$2' in:" >&2
      printf '%s' "$gh_log" >&2
      echo "  )" >&2
      failures=$((failures + 1))
    else
      echo "  ok: $1"
    fi
  }
  _check_eq() {
    if [ "$2" = "$3" ]; then
      echo "  ok: $1"
    else
      echo "  FAIL: $1 (expected '$3', got '$2')" >&2
      failures=$((failures + 1))
    fi
  }

  echo "publish_release.sh self-test"

  # A tag with no release yet takes the create path.
  gh_log=""; exists=false; create_effect=none
  publish_release v1 "1.0" "$notes" false a.bin b.bin
  _check_eq "fresh tag: create succeeds" "$?" "0"
  _check_has "fresh tag: creates the release" "release create v1 a.bin b.bin"
  _check_lacks "fresh tag: does not edit" "release edit"
  _check_lacks "fresh tag: stable release is not marked prerelease" "--prerelease"

  # A preview tag adds --prerelease on the create path.
  gh_log=""; exists=false; create_effect=none
  publish_release v1 "1.0" "$notes" true a.bin
  _check_has "preview tag: create is flagged prerelease" "--prerelease"

  # A release that already exists (the UI tag route) is completed in place.
  gh_log=""; exists=true; create_effect=none
  publish_release v1 "1.0" "$notes" true a.bin b.bin
  _check_eq "existing release: succeeds" "$?" "0"
  _check_lacks "existing release: does not re-create" "release create"
  _check_has "existing release: edits title/notes" "release edit v1 --title 1.0"
  _check_has "existing release: sets prerelease explicitly" "--prerelease=true"
  _check_has "existing release: publishes a draft" "--draft=false"
  _check_has "existing release: uploads over any partial assets" \
    "release upload v1 a.bin b.bin --clobber"

  # Clearing the prerelease flag has to be expressible, not just setting it.
  gh_log=""; exists=true; create_effect=none
  publish_release v1 "1.0" "$notes" false a.bin
  _check_has "existing release: prerelease can be cleared" "--prerelease=false"

  # An assetless release must not call `gh release upload` with no files.
  gh_log=""; exists=true; create_effect=none
  publish_release v1 "1.0" "$notes" false
  _check_eq "no assets: succeeds" "$?" "0"
  _check_lacks "no assets: skips upload" "release upload"

  # The regression this script exists for: a create that half-succeeded used
  # to poison every retry. Now attempt 2 sees the release and finishes it.
  # shellcheck source=.github/scripts/retry.sh
  source "${_PUBLISH_RELEASE_DIR}/retry.sh"
  gh_log=""; exists=false; create_effect=half-done
  RETRY_INITIAL_DELAY=0 retry publish_release v1 "1.0" "$notes" false a.bin
  _check_eq "half-done create: retry recovers" "$?" "0"
  _check_has "half-done create: first attempt tried to create" "release create"
  _check_has "half-done create: second attempt uploaded instead" \
    "release upload v1 a.bin --clobber"

  rm -f "$notes"
  unset -f gh
  if [ "$failures" -ne 0 ]; then
    echo "publish_release.sh self-test FAILED ($failures)" >&2
    return 1
  fi
  echo "publish_release.sh self-test passed"
  return 0
}

if [ "${1:-}" = "--self-test" ]; then
  _publish_release_self_test
  exit $?
fi

if [ "$#" -lt 4 ]; then
  echo "usage: publish_release.sh <tag> <title> <notes-file> <prerelease> [asset ...]" >&2
  exit 2
fi

# shellcheck source=.github/scripts/retry.sh
source "${_PUBLISH_RELEASE_DIR}/retry.sh"
retry publish_release "$@"
