#!/usr/bin/env bash
# Publishes every project folder as its own GitHub repository, with its own history.
#
#   projects/04-pii-guard  ->  github.com/dushinitspec-ux/pii-guard (branch main)
#
# This monorepo stays the source of truth: change code here, commit, then run
#   scripts/publish-projects.sh            (all projects)
#   scripts/publish-projects.sh pii-guard  (one project)
# Needs the GitHub CLI (gh) logged in with the "repo" and "workflow" scopes.
set -euo pipefail

OWNER="dushinitspec-ux"
cd "$(git rev-parse --show-toplevel)"

for dir in projects/*/; do
  dir="${dir%/}"
  slug="${dir#projects/[0-9][0-9]-}"
  if [[ $# -gt 0 && " $* " != *" $slug "* ]]; then
    continue
  fi
  echo "== $dir -> $OWNER/$slug"
  branch="publish/$slug"
  git subtree split --prefix="$dir" -b "$branch" >/dev/null
  if ! gh repo view "$OWNER/$slug" >/dev/null 2>&1; then
    echo "   repository $OWNER/$slug does not exist yet; create it first (gh repo create)" >&2
    git branch -D "$branch" >/dev/null
    exit 1
  fi
  git push --force "https://github.com/$OWNER/$slug.git" "$branch:main"
  git branch -D "$branch" >/dev/null
done
