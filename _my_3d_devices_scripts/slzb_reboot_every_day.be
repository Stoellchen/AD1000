#META {"start":1}
###############################################################################
# SLZB AUTOMATISCHER 24-STUNDEN-REBOOT WÄCHTER
###############################################################################
# BESCHREIBUNG:
# Dieses Skript zwingt das SLZB-Modul zu einem täglichen, automatischen Neustart.
# 
# WARUM DAS NÜTZLICH IST:
# 1. Bereinigt den internen Speicher und den Netzwerk-Stack (beugt Trägheit vor).
# 2. Zwingt umliegende Zigbee-Clients (z.B. Aqara/Tuya-Sensoren) einmal täglich, 
#    ihre Routing-Tabellen neu aufzubauen. Dadurch schnappen sich Sensoren viel 
#    eher das stärkere SLZB statt sich an alte Router (z.B. Third Reality) zu klammern.
###############################################################################



var delayTime = 60 * 60 * 1000 # 1 hour cycle delay
var rebootAfter = 24 # reboot after 24 hours
var timePassed = 0 # variable for storing the number of hours passed

while timePassed < rebootAfter # we execute the loop until timePassed is less than rebootAfter
  SLZB.log("time to reboot: " .. rebootAfter - timePassed .. "hours") # log some text
  SLZB.delay(delayTime) # wait delayTime
  timePassed = timePassed + 1 # increase timePassed by one more
end

SLZB.reboot() # we have reached rebootAfter, reboot the device
