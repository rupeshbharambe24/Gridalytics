#!/usr/bin/env bash
#
# gdrive-sync / sync_drive.sh — back any project up to Google Drive via rclone.
#
# THE SYSTEM (one convention for all your projects):
#   - Code              -> GitHub (rupeshbharambe24/<repo>)   [git handles this]
#   - Everything else   -> Google Drive  gdrive24:<repo-folder-name>  (top-level,
#     matching how your Drive already organizes projects). The gitignored-but-
#     precious stuff: data/ DB, .env, model artifacts, etc.
#   - Account: the rclone remote "gdrive24" points at rupeshbharambe2004@gmail.com.
#
# This script is PROJECT-AGNOSTIC: it figures out which project you're in from
# the current directory's git root (or cwd) and targets gdrive:Projects/<name>.
# So the SAME command works in every project with zero per-project config.
#
# ONE-TIME MACHINE SETUP:
#   rclone config     # new remote named "gdrive", type "drive" (Google Drive),
#                     # sign in as rupeshbharambe2004@gmail.com.
#
# PER PROJECT: nothing to configure. Just cd into it and run `gdrive-sync push`.
#   (Optional: put a `.driveignore` file in the project root — rclone exclude
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
#   FULL=1         include .venv/node_modules too (default: skip them — they
#                  rebuild via `uv sync` / `npm install` and won't run elsewhere).
#   REMOTE=gdrive              rclone remote name.
#   DRIVE_BASE=Projects        parent folder in Drive.
#   DRIVE_PATH=Projects/Foo    override the whole Drive path for this project.

set -euo pipefail

REMOTE="${REMOTE:-gdrive24}"
DRIVE_BASE="${DRIVE_BASE:-}"   # empty = top-level <name> (your Drive's layout); set e.g. "Projects" to nest
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
  EXCLUDES+=(
    --exclude ".venv/**" --exclude "**/node_modules/**"
    --exclude "**/__pycache__/**" --exclude "frontend/.next/**"
    --exclude ".pytest_cache/**" --exclude "mlflow/**"
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
