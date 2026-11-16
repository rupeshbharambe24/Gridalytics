#!/usr/bin/env bash
#
# gdrive-sync / sync_drive.sh — back any project up to Google Drive via rclone.
#
# THE SYSTEM (one convention for all your projects):
#   - Code              -> GitHub (rupeshbharambe24/<repo>)   [git handles this]
#   - Everything else   -> Google Drive  gdrive24:Projects/<repo-folder-name>
#     The gitignored-but-precious stuff: data/ DB, .env, model artifacts, etc.
#   - Account: the rclone remote "gdrive24" points at rupeshbharambe2004@gmail.com,
#     whose Drive keeps every project under one top-level "Projects/" folder.
#
# PROJECT-AGNOSTIC: it figures out which project you're in from the current
# directory's git root (or cwd) and targets gdrive24:Projects/<name>. The SAME
# command works in every project with zero per-project config.
#
# ONE-TIME MACHINE SETUP:
#   rclone config create gdrive24 drive scope=drive   # sign in as rupeshbharambe2004@gmail.com
#
# PER PROJECT: nothing to configure. cd into it and run `gdrive-sync push`.
#   (Optional: a `.driveignore` file in the project root — rclone exclude
#    patterns, one per line — to skip project-specific stuff.)
#
# SAFE BY DESIGN: runs ON DEMAND (never corrupts .git like a live cloud-sync
# folder). Work in the real repo on your fast disk; Drive is the backup/mirror.
#
# USAGE (from anywhere inside a project):
#   gdrive-sync push     # local -> Drive  (Drive mirrors local)
#   gdrive-sync pull     # Drive -> local  (adds/updates, never deletes local)
#   gdrive-sync dry      # dry-run of push (shows changes, uploads nothing)
#   gdrive-sync where    # print the project + Drive path it would use
#
# TOGGLES (env vars):
#   FULL=1         include regenerable trees too (default: skip them — see below).
#   REMOTE=gdrive24            rclone remote name.
#   DRIVE_BASE=Projects        parent folder in Drive (DEFAULT). DRIVE_BASE="" = Drive root.
#   DRIVE_PATH=Projects/Foo    override the whole Drive path for this project.

set -euo pipefail

REMOTE="${REMOTE:-gdrive24}"
DRIVE_BASE="${DRIVE_BASE:-Projects}"   # default: everything under My Drive/Projects/. Set DRIVE_BASE="" for Drive root.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
NAME="$(basename "$ROOT")"
if [[ -n "$DRIVE_BASE" ]]; then
  DRIVE_PATH="${DRIVE_PATH:-$DRIVE_BASE/$NAME}"
else
  DRIVE_PATH="${DRIVE_PATH:-$NAME}"
fi
DEST="${REMOTE}:${DRIVE_PATH}"

EXCLUDES=( --exclude ".DS_Store" --exclude "**/.DS_Store" --exclude "*.swp" )
if [[ "${FULL:-0}" != "1" ]]; then
  # Regenerable trees — excluded at ANY depth so nested repos/sub-projects are
  # covered too (rebuild via `uv sync` / `npm install` / `cargo build` / flutter).
  EXCLUDES+=(
    --exclude "**/.venv/**"
    --exclude "**/node_modules/**"
    --exclude "**/__pycache__/**"
    --exclude "**/.pytest_cache/**"
    --exclude "**/.mypy_cache/**"
    --exclude "**/.ruff_cache/**"
    --exclude "**/.next/**"
    --exclude "**/target/**"        # Rust / cargo build output (can be many GB)
    --exclude "**/build/**"         # Flutter / setuptools / generic build output
    --exclude "**/.dart_tool/**"    # Flutter
    --exclude "**/*.egg-info/**"
    --exclude "**/mlflow/**"
  )
fi
# Optional per-project extra excludes.
[[ -f "$ROOT/.driveignore" ]] && EXCLUDES+=( --exclude-from "$ROOT/.driveignore" )

COMMON=( --progress --transfers 8 --checkers 16 --drive-chunk-size 64M --fast-list )

usage() { echo "usage: gdrive-sync {push|pull|dry|where}   [FULL=1]" >&2; exit 2; }

case "${1:-}" in
  push)
    echo ">> PUSH  $NAME :  $ROOT  ->  $DEST   (FULL=${FULL:-0})"
    rclone sync "$ROOT" "$DEST" "${EXCLUDES[@]}" "${COMMON[@]}"
    echo ">> done. Drive now mirrors this project."
    ;;
  pull)
    echo ">> PULL  $NAME :  $DEST  ->  $ROOT   (copy: adds/updates, never deletes local)"
    rclone copy "$DEST" "$ROOT" "${EXCLUDES[@]}" "${COMMON[@]}"
    echo ">> done."
    ;;
  dry)
    echo ">> DRY-RUN push  $NAME :  $ROOT  ->  $DEST   (FULL=${FULL:-0})"
    rclone sync "$ROOT" "$DEST" "${EXCLUDES[@]}" "${COMMON[@]}" --dry-run
    ;;
  where)
    echo "project : $NAME"
    echo "root    : $ROOT"
    echo "drive   : $DEST"
    ;;
  *) usage ;;
esac
