#!/bin/bash
#Read Date

backup_dir="/config/scripts/pfsense/backup"
log_file="/config/scripts/pfsense/mail.txt"
list_file="/config/scripts/pfsense/pfsense.list"

datum=`date +%d-%m-%Y-%H%M`
date +"Startzeit: %d.%m.%Y %H:%M"  > mail.txt
echo " " >> mail.txt
echo " " >> mail.txt
echo "Zugriff auf folgende pfSense Firewalls:" >> mail.txt
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
		date +"$2: %d.%m.%Y %H:%M"  >> mail.txt
		/config/scripts/pfsense/pfsense-backup.sh $1 $2 $3 $datum
		sleep 1
	fi
done < /config/scripts/pfsense/pfsense.list
echo " " >> mail.txt
echo " " >> mail.txt
echo "Folgende Dateien wurden erstellt:" >> mail.txt
echo " " >> mail.txt
#List files in tftproot folder on local host and write it to mail.txt file
ls -ltr /config/scripts/pfsense/backup/ >> mail.txt
echo " " >> mail.txt
#Mount Backup Folder
mount -t cifs -o [SMB-Freigabe\ /BackupConfigs
#Check, if the mount point exist
file="/BackupConfigs/chkfile"
if [ -f "$file" ]
then
     #Delete all Configs older than 60 days (2 months)
     echo "Folgende Dateien aelter als 2 Monate wurden geloescht:" >> mail.txt
     find /BackupConfigs/*.xml -mtime +60 -print -exec rm {} \; >> mail.txt
     #Move Configs
     mv /config/scripts/pfsense/backup/*.xml /BackupConfigs
     sleep 5
     umount /BackupConfigs
else
     # figlet "ERROR" >> mail.txt
     echo "***** MOUNT-PUNKT NICHT ERREICHBAR - DATEIEN NICHT VERSCHOBEN ****" >> mail.txt
fi


date +"Endzeit: %d.%m.%Y %H:%M"  >> mail.txt
#Send Email
# mail -s "Backup pfSense Firewalls" "[mail@server.com]" < mail.txt


