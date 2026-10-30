#!/bin/bash
# Called from GitHub Actions after tests and a completed scan.
set -euo pipefail
publish_dir="$(pwd)/work/publish"
mkdir -p work
if git ls-remote --exit-code --heads origin monitor-data >/dev/null 2>&1; then
  git fetch origin monitor-data
  git worktree add --detach "$publish_dir" FETCH_HEAD
else
  git worktree add --detach "$publish_dir" HEAD
  git -C "$publish_dir" checkout --orphan monitor-data
  git -C "$publish_dir" rm -rf .
fi
mkdir -p "$publish_dir/data"
cp -R data/. "$publish_dir/data/"
rm -f "$publish_dir/data/.scan.lock"
git -C "$publish_dir" config user.name 'competition-monitor[bot]'
git -C "$publish_dir" config user.email 'competition-monitor@users.noreply.github.com'
git -C "$publish_dir" add -f data
if ! git -C "$publish_dir" diff --cached --quiet; then
  git -C "$publish_dir" commit -m "Update competition scan ${GITHUB_RUN_ID:-manual}"
  git -C "$publish_dir" push origin HEAD:refs/heads/monitor-data
fi
