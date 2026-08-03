#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Tries python3 → python → py -3 on PATH; on Windows, falls back to common
# Python install locations because Git Bash launched by some hooks gets a
# stripped PATH that omits the Windows Python directory.
#
# Windows ships fake `python3`/`python` shims under WindowsApps (the Store
# "app execution alias") that sit on PATH but don't run Python — they just
# print an error and exit non-zero. `command -v` can't tell those apart from
# a real interpreter, so every candidate is verified with `--version` before
# it's used.
#
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no Python is found — hooks must never block the AI tool.
set -u

works() { "$@" --version >/dev/null 2>&1; }

PY=""
if command -v python3 >/dev/null 2>&1 && works python3; then
  PY=python3
elif command -v python >/dev/null 2>&1 && works python; then
  PY=python
elif command -v py >/dev/null 2>&1 && works py -3; then
  PY="py -3"
else
  # PATH lookup failed (or only found broken shims) — probe standard
  # Windows install locations.
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    if [ -x "$cand" ] && works "$cand"; then PY="$cand"; break; fi
  done
  shopt -u nullglob 2>/dev/null || true
  [ -n "$PY" ] || exit 0
fi

# shellcheck disable=SC2086
exec $PY "$@"
