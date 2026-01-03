#!/usr/bin/env bash
set -euo pipefail

# HA-safe environment
export HOME=/root
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

cd /config

MSG="${1:-HA trigger: git update}"

git add .

git commit -m "$MSG" || {
  echo "Nothing to commit"
  exit 0
}

GIT_SSH_COMMAND="/usr/bin/ssh -i /root/.ssh/id_ed25519 \
  -o UserKnownHostsFile=/config/.ssh/known_hosts \
  -o StrictHostKeyChecking=yes" \
git push