### ANLEITUNG / BENUTZUNG:
### -----------------------------------------------------------------------------------
###
### Kopiere den gesamten folgenden Block (ab 'cat << 'EOF' ...' bis ganz nach unten)
### und füge ihn am Stück in die Kommandozeile (SSH) deines Proxmox-Nodes ein.
### Das Skript wird vollautomatisch erstellt, ausführbar gemacht und der Cronjob
### für täglich um 09:22 Uhr wird eingerichtet.
###
### -----------------------------------------------------------------------------------
#
#
#

cat << 'EOF' > /usr/local/bin/pve_clean_backup_trash.sh
#!/bin/bash
###############################################################################
# Proxmox-Backup-Müll-Wächter (Fehlerfreie Version ohne Klammern)
# Löscht verwaiste .tmp Ordner und unvollständige .dat / .vma.dat / .tar.dat Leichen,
# die älter als 2 Tage (+48h) sind.
#
# NUTZUNG:
#   Normaler Modus (Cron): /usr/local/bin/pve_clean_backup_trash.sh
#   Test-Modus (Dry-Run):  /usr/local/bin/pve_clean_backup_trash.sh --dry-run (oder -d)
###############################################################################

TARGET_DIR="/var/lib/vz/dump"
DRY_RUN=false

# Flag-Abfrage am Anfang
if [ "$1" == "--dry-run" ] || [ "$1" == "-d" ]; then
    DRY_RUN=true
    echo -e "\n\e[1;33m⚠️  DRY-RUN MODUS AKTIV: Es wird NICHTS gelöscht! ⚠️\e[0m\n"
fi

# Sicherheitscheck: Existiert das Verzeichnis überhaupt?
if [ ! -d "$TARGET_DIR" ]; then
    echo "ERROR: Verzeichnis $TARGET_DIR existiert nicht auf diesem Node."
    exit 1
fi

echo "=== STAGE 1: Abgebrochene .tmp Verzeichnisse (> 2 Tage) ==="
if [ "$DRY_RUN" = true ]; then
    find "$TARGET_DIR" -type d -name "*.tmp" -mtime +1 -print
else
    find "$TARGET_DIR" -type d -name "*.tmp" -mtime +1 -print -exec rm -rf {} +
fi

echo -e "\n=== STAGE 2: Unvollständige .dat / .vma.dat / .tar.dat Trümmer (> 2 Tage) ==="
for ext in "*.dat" "*.vma.dat" "*.tar.dat"; do
    if [ "$DRY_RUN" = true ]; then
        find "$TARGET_DIR" -type f -name "$ext" -mtime +1 -print
    else
        find "$TARGET_DIR" -type f -name "$ext" -mtime +1 -print -exec rm -f {} +
    fi
done

echo -e "\n=== STAGE 3: Abgeschnittene vzdump-Dateien ohne korrekte Endung (> 2 Tage) ==="
if [ "$DRY_RUN" = true ]; then
    find "$TARGET_DIR" -type f -name "vzdump-*" ! -name "*.zst" ! -name "*.log" ! -name "*.notes" -mtime +1 -print
else
    find "$TARGET_DIR" -type f -name "vzdump-*" ! -name "*.zst" ! -name "*.log" ! -name "*.notes" -mtime +1 -print -exec rm -f {} +
fi

echo -e "\n=== Bereinigung abgeschlossen! ==="

# INFO-BLOCK AM ENDE AUSGEBEN
echo -e "\n\e[1;36mℹ️  HILFE-INFO:\e[0m"
echo "Um zu testen, was gelöscht werden würde, nutze diesen Befehl:"
echo "/usr/local/bin/pve_clean_backup_trash.sh --dry-run"

echo -e "\n\e[1;36mℹ️  AKTUELLER CRONJOB (crontab -l):\e[0m"
crontab -l 2>/dev/null | grep -E "pve_clean_backup_trash.sh|##|^[0-9]"
echo ""
EOF

# 2. Skript ausführbar machen
chmod +x /usr/local/bin/pve_clean_backup_trash.sh

# 3. Alte Einträge dieses Skripts aus der Crontab entfernen (verhindert Duplikate)
crontab -l 2>/dev/null | grep -v "pve_clean_backup_trash.sh" | crontab -

# 4. Neuen Cronjob für täglich exakt um 09:22 Uhr hinzufügen
(crontab -l 2>/dev/null; echo "22 9 * * * /usr/local/bin/pve_clean_backup_trash.sh > /dev/null 2>&1") | crontab -

echo -e "\n\e[1;32m✅ Skript erstellt, Rechte gesetzt und Cronjob für 09:22 Uhr ist scharf geschaltet.\e[0m\n"

crontab -l 
