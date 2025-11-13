#!/usr/bin/env bash
set -euo pipefail
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
rsync -a --exclude='.git' ./ "$TMP_DIR/repo" >/dev/null
pushd "$TMP_DIR/repo" >/dev/null
RESP=$(cat tests/fixtures/graphql-response.json)
COMMITS=$(echo "$RESP" | jq -r '((.data.user.contributionsCollection.totalCommitContributions // 0) + (.data.user.contributionsCollection.restrictedContributionsCount // 0))')
PRS=$(echo "$RESP" | jq -r '(.data.user.pullRequests.totalCount // 0)')
ISSUES=$(echo "$RESP" | jq -r '(.data.user.issues.totalCount // 0)')
REPOS=$(echo "$RESP" | jq -r '(.data.user.repositories.totalCount // 0)')
export COMMITS PRS ISSUES REPOS
TS="2025-01-01T00:00:00Z"
apply_sed() {
  local file="$1"
  sed -i.bak -E "s/(<!--stat:commits-->).*(<!--\\/stat:commits-->)/\\1${COMMITS}\\2/" "$file"
  sed -i.bak -E "s/(<!--stat:prs-->).*(<!--\\/stat:prs-->)/\\1${PRS}\\2/" "$file"
  sed -i.bak -E "s/(<!--stat:issues-->).*(<!--\\/stat:issues-->)/\\1${ISSUES}\\2/" "$file"
  sed -i.bak -E "s/(<!--stat:repos-->).*(<!--\\/stat:repos-->)/\\1${REPOS}\\2/" "$file"
  sed -i.bak -E "s/<!--updated: .*-->/<!--updated: ${TS}-->/" "$file"
  rm -f "$file.bak"
}
apply_sed README.md
apply_sed docs/index.html
rg --fixed-strings "<!--stat:commits-->${COMMITS}" README.md >/dev/null
rg --fixed-strings "<!--stat:prs-->${PRS}" README.md >/dev/null
rg --fixed-strings "<!--stat:issues-->${ISSUES}" docs/index.html >/dev/null
rg --fixed-strings "<!--stat:repos-->${REPOS}" docs/index.html >/dev/null
popd >/dev/null
