#!/usr/bin/env bash
# Warn when a feat: commit has landed since the last v* release tag while
# CHANGELOG.md's [Unreleased] section is still empty — a MINOR-or-higher
# change shipped with no release notes to show for it.
#
# Only feat: commits trigger this. fix:/chore:/docs:/refactor: commits don't
# force an entry — CHANGELOG.md has always been curated as user-facing
# highlights, not a mirror of every commit, and forcing an entry for routine
# internal fixes would just train people to write a throwaway line to get
# past the check.
#
# Non-blocking by design (see .gitlab-ci.yml's check-changelog-sync job) —
# this is a nudge at merge time, not a hard gate. The hard gate is
# scripts/verify-release-tag.sh, run when a release tag is actually pushed.
#
# Usage: scripts/check-changelog-sync.sh
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

last="$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || true)"
range="${last:+${last}..}HEAD"

feats="$(git log "$range" --format='%s' | grep -E '^feat(\([^)]*\))?!?:' || true)"

if [ -z "$feats" ]; then
  echo "No feat: commits since ${last:-the beginning} — nothing to check."
  exit 0
fi

unreleased="$(awk '
  /^## \[Unreleased\]/ { flag = 1; next }
  flag && /^## \[/ { flag = 0 }
  flag { print }
' CHANGELOG.md | tr -d '[:space:]')"

if [ -z "$unreleased" ]; then
  echo "WARNING: feat: commit(s) landed since ${last:-the beginning} but"
  echo "CHANGELOG.md's [Unreleased] section is empty:"
  printf '%s\n' "$feats" | sed 's/^/  /'
  echo
  echo "Add a summary to CHANGELOG.md's [Unreleased] section."
  exit 1
fi

echo "OK: [Unreleased] has content and feat: commit(s) are present since ${last:-the beginning}."
