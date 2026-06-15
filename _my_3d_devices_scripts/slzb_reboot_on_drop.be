#META {"start":1}
###############################################################################
# SLZB ZIGBEE-CHIP VERBINDUNGS-WÄCHTER (WATCHDOG)
###############################################################################
# BESCHREIBUNG:
# Dieses Skript überwacht permanent die Socket-Verbindung der Zigbee-Clients.
#
# WIE ES FUNKTIONIERT:
# Es prüft alle 500 Millisekunden, ob noch aktive Verbindungen (z.B. zu 
# Zigbee2MQTT) bestehen. Wenn die Verbindung plötzlich auf 0 abfällt, erkennt
# das Skript den Verbindungsabbruch und startet gezielt den Zigbee-Funkchip 
# neu (ZB.reboot), um den Datenfluss sofort und vollautomatisch wiederzubeleben.
#
# VORTEIL:
# Verhindert, dass das Zigbee-Netzwerk nach einem HA-Neustart oder einem 
# Netzwerk-Schlucker dauerhaft offline bleibt.
###############################################################################



#Insert your code below#META {"start":1}
import ZB # import zb module
var lastSocketClients = 0 # variable to remember the number of connected clients

#An infinite loop is needed to keep the script running forever.
#If execution reaches the end of the file, the script will terminate.
while true
  var curClients = ZB.getZbClients() # store current clients

  if curClients == 0 && lastSocketClients > 0 # if there are no current clients and there were in the last cycle, it means that the clients has disconnected
    SLZB.log("socket client dissconnected!" ) # log some text
    ZB.reboot() # reboot zigbee chip
    SLZB.delay(5000) # 5 Sekunden Extra-Pause, damit der Chip in Ruhe hochfahren kann
  end

  lastSocketClients = curClients # store current clients
  SLZB.delay(500); # sleep for 500ms
end