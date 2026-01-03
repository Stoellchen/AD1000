#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Git Update Script für AD1000
#
# Zweck:
# - Commit & Push NUR wenn Änderungen vorhanden sind
# - Commit-Message wird als Parameter $1 übergeben
#
# Aufruf:
#   git_update_ad1000.sh "Commit message"
# -----------------------------------------------------------------------------
#
# 2

set -e

cd /config

# Default Commit-Message, falls nichts übergeben wird
MSG="${1:-HA trigger: git update}"

# Prüfen, ob Änderungen vorhanden sind
if git diff --quiet; then
  echo "No changes detected – nothing to commit."
  exit 0
fi

git add .
git commit -m "$MSG"
git push


