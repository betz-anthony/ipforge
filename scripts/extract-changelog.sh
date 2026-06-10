#!/usr/bin/env bash
# Extract the release-notes body for a version from CHANGELOG.md.
# Usage: scripts/extract-changelog.sh <version>   (version WITHOUT leading 'v')
# Prints the matching "## [<version>]" section body to stdout. If the section
# is empty or missing, prints the fallback line "Release v<version>.".
# Shared by .github/workflows/release.yml and tests/test_changelog_extract.py.
set -euo pipefail

version="${1:?usage: extract-changelog.sh <version>}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
changelog="$root/CHANGELOG.md"

notes="$(awk -v v="$version" '
  $0 ~ "^## \\[" v "\\]" { flag = 1; next }
  flag && (/^## \[/ || /^\[[^]]+\]: /) { flag = 0 }
  flag { print }
' "$changelog")"

# Drop leading blank lines.
notes="$(printf '%s\n' "$notes" | sed -e '/./,$!d')"

if [ -z "$(printf '%s' "$notes" | tr -d '[:space:]')" ]; then
  printf 'Release v%s.\n' "$version"
else
  printf '%s\n' "$notes"
fi
