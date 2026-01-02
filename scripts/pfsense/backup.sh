#!/bin/bash
#Read Date

# Sicherstellen, dass "expect" installiert ist
if ! command -v expect >/dev/null 2>&1; then
    echo "→ installing expect..."
    apk add --no-cache expect
fi

backup_dir="/config/scripts/pfsense/backup"
log_file="/config/scripts/pfsense/mail.txt"
list_file="/config/scripts/pfsense/pfsense.list"

# datum=`date +%d-%m-%Y-%H%M`
datum=`date +%Y-%m-%d-%H%M`
date +"Startzeit: %d.%m.%Y %H:%M"  > "$log_file"
echo " " >> "$log_file"
echo " " >> "$log_file"
echo "Zugriff auf folgende pfSense Firewalls:" >> "$log_file"
#Read each line in pfsense.list
while read line
do
	case "$line" in
		"#"*) ;;
		*) zeile=$line;;
	esac
    #Split each line into IP, Name, Password
    IFS=","
	set - $zeile
	if [ -n "$zeile" ]; then
		#Open pfsense-backup.sh with Parameters (File to establish connection to each pfSense and transfer Running Config to tftproot folder on local host)
		#1. IP-Address of the pfSense,2. Name of the pfSense, 3. Password, 4. Date
		date +"$2: %d.%m.%Y %H:%M"  >> "$log_file"
		/config/scripts/pfsense/pfsense-backup.sh $1 $2 $3 $datum
		sleep 1
	fi
done < "$list_file"
echo " " >> "$log_file"
echo " " >> "$log_file"
echo "Folgende Dateien wurden erstellt:" >> "$log_file"
echo " " >> "$log_file"
#List files in tftproot folder on local host and write it to "$log_file" file
ls -ltr /config/scripts/pfsense/backup/ >> "$log_file"
echo " " >> "$log_file"
#Mount Backup Folder
mount -t cifs -o [SMB-Freigabe\ /BackupConfigs
#Check, if the mount point exist
file="/BackupConfigs/chkfile"


# === Lokale Aufräumlogik: nur 30 Dateien behalten ===
echo -e "\n\nPrüfe lokale Backup-Anzahl (max. 30 Dateien)..." >> "$log_file"
count=$(ls -1 "$backup_dir"/*.xml 2>/dev/null | wc -l)
if [ "$count" -gt 90 ]; then
    remove=$((count - 90))
    echo "Es gibt $count Backups, lösche die ältesten $remove ..." >> "$log_file"
    ls -1t "$backup_dir"/*.xml | tail -n "$remove" | while read -r oldfile; do
        echo "→ Entferne $oldfile" >> "$log_file"
        rm -f "$oldfile"
    done
else
    echo "Nur $count Dateien vorhanden, keine Löschung nötig." >> "$log_file"
fi



if [ -f "$file" ]
then
     #Delete all Configs older than 60 days (2 months)
     echo "Folgende Dateien aelter als 2 Monate wurden geloescht:" >> "$log_file"
     find /BackupConfigs/*.xml -mtime +60 -print -exec rm {} \; >> "$log_file"
     #Move Configs
     mv /config/scripts/pfsense/backup/*.xml /BackupConfigs
     sleep 5
     umount /BackupConfigs
else
     # figlet "ERROR" >> "$log_file"
     echo "***** MOUNT-PUNKT NICHT ERREICHBAR - DATEIEN NICHT VERSCHOBEN ****" >> "$log_file"
fi


date +"Endzeit: %d.%m.%Y %H:%M"  >> "$log_file"
#Send Email
# mail -s "Backup pfSense Firewalls" "[mail@server.com]" < "$log_file"


