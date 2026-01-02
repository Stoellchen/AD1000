#!/usr/bin/expect
set timeout 20
#Set Variables
#set var_IP [lindex $argv 0]
#   install expect mit:     apk add expect
#   

set var_Name [lindex $argv 1]
set var_Pass [lindex $argv 2]
set var_Datum [lindex $argv 3]

# spawn scp -P [Port für SSH] [lindex $argv 0]:/cf/conf/config.xml /config/scripts/pfsense/backup/config-$var_Datum-$var_Name.xml
spawn scp -P 22 [lindex $argv 0]:/cf/conf/config.xml /config/scripts/pfsense/backup/config-$var_Datum-$var_Name.xml
expect {
  -re ".*es.*o.*" {
    exp_send "yes\r"
    exp_continue
  }
  -re ".*sword.*" {
    exp_send "$var_Pass\r"
  }
}
expect eod
exit


