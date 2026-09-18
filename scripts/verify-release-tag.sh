#!/usr/bin/env bash
# Hard gate at release-tag time: a pushed v* tag must (a) match the version
# scripts/suggest-bump.sh computes from commits since the PREVIOUS release
# tag, and (b) have a real (non-placeholder) CHANGELOG.md section. Run by
# .gitlab-ci.yml's verify-release-tag job, which mirror_github depends on —
# a wrong version number or an empty changelog entry must not reach the
# public GitHub release flow.
#
# Usage: scripts/verify-release-tag.sh <tag>   (tag WITH leading 'v', e.g. v1.3.0)
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

tag="${1:?usage: verify-release-tag.sh <vX.Y.Z>}"
version="${tag#v}"

if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "'$tag' isn't a vX.Y.Z release tag — nothing to verify."
  exit 0
fi

# Previous release tag by version order, not commit reachability — git
# describe from the tagged commit itself would just return this tag. Avoids
# bash 4's mapfile/arrays so this also runs under macOS's stock bash 3.2.
matched="$(git tag --list 'v[0-9]*' --sort=-v:refname | grep -A1 -x -- "$tag" || true)"
if [ "$(printf '%s\n' "$matched" | wc -l)" -ge 2 ]; then
  prev="$(printf '%s\n' "$matched" | sed -n '2p')"
else
  prev=""
fi

if [ -z "$prev" ]; then
  echo "$tag is the first v* release tag found — nothing to compare against. Skipping bump check."
else
  echo "Checking $tag's version against commits since $prev..."
  suggestion="$(scripts/suggest-bump.sh "$prev" "$tag")"
  echo "$suggestion"
  expected="$(printf '%s\n' "$suggestion" | awk '/^Next version:/ {print $3}')"
  if [ "$expected" != "$tag" ]; then
    echo
    echo "ERROR: $tag does not match the recommended bump ($expected) for commits since $prev."
    echo "  Delete and re-push the tag with the correct version."
    exit 1
  fi
  echo "OK: $tag matches the recommended bump."
fi

echo
echo "Checking CHANGELOG.md has a real entry for $version..."
notes="$(scripts/extract-changelog.sh "$version")"
placeholder="Release v${version}."
if [ "$notes" = "$placeholder" ]; then
  echo
  echo "ERROR: CHANGELOG.md has no '## [$version]' section, or it's empty."
  echo "  Add release notes to CHANGELOG.md before tagging, then retag."
  exit 1
fi
echo "OK: CHANGELOG.md has a real entry for $version."
echo
echo "$notes"
