#!/usr/bin/env bash
set -euo pipefail

# ---------- HA-safe environment ----------
export HOME=/root
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

LOG="/config/logs/git.log"
mkdir -p /config/logs

NOW=$(date +"%d/%m/%Y %H:%M")
echo "[$NOW] Git Update start" > "$LOG"

cd /config

# ---------- rsync AppDaemon to config mirror start ---------- ##################################################
# -a                        Rechte, Zeiten, Struktur behalten
# -v                        sichtbar im Log
# --delete                  echtes Mirror (sehr wichtig!)
# --exclude __pycache__     Python-Müll
# --exclude *.pyc           dito
# kein -L                   keine Symlinks auflösen
APPD_SRC="/addon_configs/a0d7b954_appdaemon/"
APPD_DST="/config/__appdaemon-mirror/"

echo "[${NOW}] rsync AppDaemon → config mirror" >> /config/logs/git.log 2>&1
echo "[${NOW}] SRC: $APPD_SRC" >> /config/logs/git.log 2>&1
echo "[${NOW}] DST: $APPD_DST" >> /config/logs/git.log 2>&1
if [ -d "$APPD_SRC" ]; then
  #  --dry-run nach -- delete um zu testen, was passieren würde
  rsync -av --delete  --dry-run \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='*.log' \
    "$APPD_SRC" "$APPD_DST" >> /config/logs/git.log 2>&1
  echo "[${NOW}] rsync AppDaemon DONE" >> /config/logs/git.log 2>&1
else
  echo "[${NOW}] ERROR: AppDaemon source not found: $APPD_SRC" >> /config/logs/git.log 2>&1
fi
# ---------- rsync AppDaemon to config mirror end ---------- ####################################################



# ---------- fake_secrets ----------
if [ -x "/config/scripts/make_fake_secrets.sh" ]; then
  echo "[$NOW] Running make_fake_secrets.sh" >> "$LOG"
  /config/scripts/make_fake_secrets.sh >> "$LOG" 2>&1
else
  echo "[$NOW] WARNING: make_fake_secrets.sh not found or not executable" >> "$LOG"
fi

# ---------- SSH / known_hosts ----------
KNOWN_HOSTS="/config/.ssh/known_hosts"
# SSH_KEY="/root/.ssh/id_ed25519"
SSH_KEY="/config/.ssh/id_ed25519"

mkdir -p /config/.ssh
touch "$KNOWN_HOSTS"
chmod 600 "$KNOWN_HOSTS"

if ! grep -q github.com "$KNOWN_HOSTS"; then
  echo "[$NOW] Adding github.com to known_hosts" >> "$LOG"
  ssh-keyscan github.com >> "$KNOWN_HOSTS" 2>>"$LOG"
else
  echo "[$NOW] github.com already in known_hosts" >> "$LOG"
fi

echo "[$NOW] known_hosts content:" >> "$LOG"
grep github.com "$KNOWN_HOSTS" >> "$LOG" 2>&1

# ---------- Git identity ----------
git config --global user.name "Stoellchen"
git config --global user.email "homeassistantgithub-reg@zwooky.com"

# ---------- Commit message ----------
MSG="${1:-Minor Edit}"

# ---------- Changes check ----------
if [ -z "$(git status --porcelain)" ]; then
  echo "[$NOW] No changes detected – nothing to commit" >> "$LOG"
  exit 0
fi

# ---------- Git add / commit ----------
echo "[$NOW] git add ." >> "$LOG"
git add . >> "$LOG" 2>&1

echo "[$NOW] git commit -m \"$MSG\"" >> "$LOG"
git commit -m "$MSG" >> "$LOG" 2>&1

# ---------- Git push (EXPLICIT SSH!) ----------
echo "[$NOW] git push origin main" >> "$LOG"

GIT_SSH_COMMAND="/usr/bin/ssh \
  -i $SSH_KEY \
  -o UserKnownHostsFile=$KNOWN_HOSTS \
  -o StrictHostKeyChecking=yes" \
git push origin main >> "$LOG" 2>&1

echo "[$NOW] Git Update finished successfully" >> "$LOG"