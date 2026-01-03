#!/usr/bin/env sh


## https://community.home-assistant.io/t/sharing-your-configuration-on-github/195144/38


NOW=$(date +"%d/%m/%Y %H:%M")
echo "${NOW} Git Update" > /config/logs/git.log 2>&1

# set's the WDIR to the current directory (location of the script)
WDIR=$(cd `dirname $0` && pwd)
ROOT=$(dirname ${WDIR})

# Update fake_secrets.yaml
#echo "Updating fake_secrets.yaml"
if [ -x "${WDIR}/make_fake_secrets.sh" ]; then
  "${WDIR}/make_fake_secrets.sh"
else
    echo "Error: make_fake_secrets.sh not found or not executable"
    echo "${NOW} Error: make_fake_secrets.sh not found or not executable" >> /config/logs/git.log 2>&1
  # exit 1
fi

# Ensure github.com is in the known_hosts files
# this is required as every upgrade of HA resets this
KNOWN_HOSTS_FILE="/root/.ssh/known_hosts"
HOST="github.com"

# Check if the host is already in known_hosts
if ! grep -q "$HOST" "$KNOWN_HOSTS_FILE"; then
    echo "Adding $HOST to known_hosts..."
    echo "${NOW} Adding $HOST to known_hosts..." >> /config/logs/git.log 2>&1
    ssh-keyscan "$HOST" >> "$KNOWN_HOSTS_FILE"
else
    echo "$HOST already present in known_hosts."
    echo "${NOW} $HOST already present in known_hosts." > /config/logs/git.log 2>&1
fi


# Git config
    echo "${NOW} git config --global user.name Stoellchen" >> /config/logs/git.log 2>&1
    git config --global user.name Stoellchen
    echo "${NOW} git config --global user.email homeasssistantgithub-reg@zwooky.com" >> /config/logs/git.log 2>&1
    git config --global user.email homeasssistantgithub-reg@zwooky.com
 
# Add new files
git add . >> /config/logs/git.log 2>&1
echo "-----> git add done"

git status >> /config/logs/git.log 2>&1
echo "-----> git status done"

# Use first argument as commit message, or prompt if missing/blank
if [ -n "$1" ]; then
  CHANGE_MSG="$1"
else
  echo -n "Enter the Description for the Change: [Minor Edit] "
  read CHANGE_MSG
  CHANGE_MSG=${CHANGE_MSG:-Minor Edit}
fi

# Commit and push
git commit -m "${CHANGE_MSG}" >> /config/logs/git.log 2>&1
echo "-----> git commit done"

git push origin main >> /config/logs/git.log 2>&1
echo "-----> git push done"
echo "-----> all done"