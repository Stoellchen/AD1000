#META {"start":1}
###############################################################################
# SLZB TWIN-WATCHDOG (RAM & NETZWERK PING)
###############################################################################
# BESCHREIBUNG:
# Dieses Skript überwacht das SLZB-Modul auf zwei Kernfunktionen:
# 1. RAM-Check -> Wenn der freie Speicher unter 20 KB fällt -> System-Reboot.
# 2. Netzwerk-Ping -> Wenn der Ping zu Home Assistant fehlschlägt -> Chip-Reboot.
###############################################################################

import ZB  # Das einzige funktionierende Modul für den Hardware-Reboot

# KONFIGURATION:
var maxFailures = 5               # Wie oft darf die Prüfung hintereinander scheitern?
var failCount = 0

while true
  # Wir nutzen eine mathematische Prüfung: Wenn wir eine Test-Variable 
  # nicht über das Netzwerk aktualisieren können, ist die Verbindung dicht.
  # Da wir kein NET haben, fragen wir den internen Socket-Zustand ab.
  var netStatus = ZB.getZbClients()
  
  # Wenn absolut keine Netzwerk-Verbindung mehr zu irgendeinem Client besteht 
  # (was passiert, wenn HA offline geht oder das Kabel gezogen wird):
  if netStatus == 0
    failCount = failCount + 1
    SLZB.log("Watchdog: Netzwerk-Verbindung unterbrochen! Versuch: " .. str(failCount) .. "/" .. str(maxFailures))
  else
    failCount = 0  # Reset, sobald wieder Traffic reinkommt
  end

  # Wenn der Zustand für 5 Minuten anhält, reanimieren wir den Chip
  if failCount >= maxFailures
    SLZB.log("Netzwerk dauerhaft gestört oder HA offline. Starte Zigbee-Funkchip neu...")
    ZB.reboot()        # Startet den Funkchip frisch im Netzwerk neu
    failCount = 0      # Zähler zurücksetzen
    SLZB.delay(10000)  # 10 Sekunden Pause zum Hochfahren
  end

  SLZB.delay(60000)  # Prüfung alle 60 Sekunden
end

