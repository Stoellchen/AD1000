#!/usr/bin/env bash
set -euo pipefail

# HA-safe environment
export HOME=/root
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin


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
# 5

set -e

cd /config

# Default Commit-Message, falls nichts übergeben wird
MSG="${1:-HA trigger: git update}"

# Prüfen, ob Änderungen vorhanden sind
# if git diff --quiet; then
#  echo "No changes detected – nothing to commit."
#  exit 0
#fi

git add .
git commit -m "$MSG"

GIT_SSH_COMMAND="/usr/bin/ssh -i /root/.ssh/id_ed25519 -o UserKnownHostsFile=/config/.ssh/known_hosts -o StrictHostKeyChecking=yes" \
git push

