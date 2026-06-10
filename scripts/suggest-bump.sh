#!/usr/bin/env bash
# Suggest the next SemVer version from Conventional Commits since the last v* tag.
#
#   MAJOR  if any commit has a `!` suffix (e.g. feat(api)!:) or a
#          "BREAKING CHANGE:" footer.
#   MINOR  else if any commit is a feat (feat: / feat(scope):).
#   PATCH  else if there are any commits (fix/perf/refactor/docs/chore/…).
#
# Note: per CONTRIBUTING.md, a breaking REST API change ships as a new /api/vN
# (a feat → MINOR) and is NOT marked `!`. Reserve `!` / BREAKING CHANGE for
# app-level incompatibilities (feature/endpoint removal, irreversible DB
# migration, config/CLI breaks) — those are the ones that should bump MAJOR.
#
# Usage: scripts/suggest-bump.sh
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

last="$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || true)"

if [ -n "$last" ]; then
  range="${last}..HEAD"
  base="${last#v}"
else
  range="HEAD"
  base="0.0.0"
  echo "No v* tag found — treating base version as 0.0.0 over full history."
fi

# Commit count in range.
count="$(git rev-list --count "$range" 2>/dev/null || echo 0)"
if [ "$count" -eq 0 ]; then
  echo "No commits since ${last:-the beginning}. Nothing to release."
  exit 0
fi

subjects="$(git log "$range" --format='%s')"
bodies="$(git log "$range" --format='%B')"

# Conventional-commit type detector. A header looks like:
#   type(optional-scope)!: subject     OR     type!: subject
major_re='^[a-z]+(\([^)]*\))?!:'
minor_re='^[a-z]+(\([^)]*\))?:'   # refined to feat below

bump="patch"
reason="only fix/chore/docs/refactor-type commits"

if printf '%s\n' "$subjects" | grep -Eq "$major_re" \
   || printf '%s\n' "$bodies" | grep -Eq '(^|[[:space:]])BREAKING[ -]CHANGE:'; then
  bump="major"
  reason="a '!' breaking-change suffix or BREAKING CHANGE footer"
elif printf '%s\n' "$subjects" | grep -Eq '^feat(\([^)]*\))?!?:'; then
  bump="minor"
  reason="a feat: commit (new functionality)"
fi

IFS='.' read -r M m p <<EOF
$base
EOF
M="${M:-0}"; m="${m:-0}"; p="${p:-0}"

case "$bump" in
  major) next="$((M + 1)).0.0" ;;
  minor) next="${M}.$((m + 1)).0" ;;
  patch) next="${M}.${m}.$((p + 1))" ;;
esac

echo "Last release:   ${last:-<none>}"
echo "Commits since:  ${count}"
echo "Recommended:    ${bump}  (because: ${reason})"
echo "Next version:   v${next}"
echo
echo "Deciding commits:"
case "$bump" in
  major) printf '%s\n' "$subjects" | grep -E "$major_re" | sed 's/^/  /' || true
         printf '%s\n' "$bodies" | grep -E '(^|[[:space:]])BREAKING[ -]CHANGE:' | sed 's/^/  /' || true ;;
  minor) printf '%s\n' "$subjects" | grep -E '^feat(\([^)]*\))?!?:' | sed 's/^/  /' || true ;;
  patch) printf '%s\n' "$subjects" | sed 's/^/  /' ;;
esac
