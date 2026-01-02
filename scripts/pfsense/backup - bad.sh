#!/bin/bash
# pfSense Backup Script
# Behält lokal nur die letzten 30 Backups

# === Variablen ===
datum=$(date +%d-%m-%Y-%H%M)
backup_dir="/config/scripts/pfsense/backup"
log_file="/config/scripts/pfsense/mail.txt"
list_file="/config/scripts/pfsense/pfsense.list"

# === Start Logging ===
date +"Startzeit: %d.%m.%Y %H:%M" > "$log_file"
echo -e "\n\nZugriff auf folgende pfSense Firewalls:" >> "$log_file"

# === Hauptschleife ===
while read -r line; do
    case "$line" in
        "#"*|"") continue ;;  # Kommentare und leere Zeilen überspringen
    esac

    IFS="," read -r ip name pass <<< "$line"

    if [ -n "$ip" ] && [ -n "$name" ]; then
        date +"$name: %d.%m.%Y %H:%M" >> "$log_file"
        /config/scripts/pfsense/pfsense-backup.sh "$ip" "$name" "$pass" "$datum"
        sleep 1
    fi
done < "$list_file"

# === Liste der erstellten Dateien ===
echo -e "\n\nFolgende Dateien wurden erstellt:\n" >> "$log_file"
ls -ltr "$backup_dir" >> "$log_file"

# === Lokale Aufräumlogik: nur 30 Dateien behalten ===
echo -e "\n\nPrüfe lokale Backup-Anzahl (max. 30 Dateien)..." >> "$log_file"
count=$(ls -1 "$backup_dir"/*.xml 2>/dev/null | wc -l)

if [ "$count" -gt 30 ]; then
    remove=$((count - 90))
    echo "Es gibt $count Backups, lösche die ältesten $remove ..." >> "$log_file"
    ls -1t "$backup_dir"/*.xml | tail -n "$remove" | while read -r oldfile; do
        echo "→ Entferne $oldfile" >> "$log_file"
        rm -f "$oldfile"
    done
else
    echo "Nur $count Dateien vorhanden, keine Löschung nötig." >> "$log_file"
fi

# === CIFS Mount (optional, falls aktiv) ===
mount -t cifs -o [SMB-Freigabe] /BackupConfigs
file="/BackupConfigs/chkfile"

if [ -f "$file" ]; then
    echo -e "\nFolgende Dateien älter als 60 Tage wurden gelöscht:" >> "$log_file"
    find /BackupConfigs/*.xml -mtime +60 -print -exec rm {} \; >> "$log_file"

    echo -e "\nVerschiebe aktuelle Backups nach /BackupConfigs ..." >> "$log_file"
    mv "$backup_dir"/*.xml /BackupConfigs
    sleep 5
    umount /BackupConfigs
else
    echo -e "\n***** MOUNT-PUNKT NICHT ERREICHBAR - DATEIEN NICHT VERSCHOBEN ****" >> "$log_file"
fi

# === Ende ===
date +"Endzeit: %d.%m.%Y %H:%M" >> "$log_file"

# === Mailversand (optional) ===
# mail -s "Backup pfSense Firewalls" "[mail@server.com]" < "$log_file"




