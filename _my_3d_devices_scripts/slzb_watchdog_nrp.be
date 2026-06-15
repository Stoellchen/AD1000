###############################################################################
# SLZB ULTRA-STABILITÄTS-WÄCHTER (RAM & NETZWERK PING)
###############################################################################
# BESCHREIBUNG:
# Dieses Skript überwacht zwei kritische Systemwerte:
# 1. Den freien Arbeitsspeicher (RAM) -> Reboot bei akutem Mangel (< 20KB frei).
# 2. Die Netzwerkverbindung -> Ping-Test zu Home Assistant / Gateway. 
#    Wenn 5 Pings scheitern, wird das Netzwerk neu gestartet.
###############################################################################

#META {"start":1}
import SYS  # Importiert die System-Funktionen
import NET  # Importiert die Netzwerk-Funktionen

# KONFIGURATION:
var targetIp = "10.231.9.100"     # HIER die IP deines Home Assistant eintragen!
var minFreeRam = 20000            # Mindestens 20 KB RAM müssen frei bleiben
var maxPingFailures = 5           # Wie oft darf der Ping fehlschlagen?
var pingFailCount = 0

while true
  # --- CHECK 1: Arbeitsspeicher-Überwachung ---
  var freeRam = SYS.getFreeRam()  # Holt den aktuellen freien RAM in Bytes
  if freeRam < minFreeRam
    SLZB.log("WARNUNG: Arbeitsspeicher kritisch niedrig (" .. freeRam .. " Bytes)! Erzwungener Reboot.")
    SLZB.delay(2000)
    SLZB.reboot()  # Komplett-Reboot des Geräts, um RAM zu leeren
  end

  # --- CHECK 2: Netzwerk-Überwachung (Ping-Test) ---
  var pingStatus = NET.ping(targetIp)  # Sendet einen Ping an den Server
  
  if pingStatus == false
    pingFailCount = pingFailCount + 1
    SLZB.log("Netzwerk-Ping fehlgeschlagen! Fehlversuche: " .. pingFailCount .. "/" .. maxPingFailures)
  else
    pingFailCount = 0  # Reset bei erfolgreichem Ping
  fi

  # Wenn das Netzwerk dauerhaft weg ist, starten wir den Netzwerk-Stack neu
  if pingFailCount >= maxPingFailures
    SLZB.log("Netzwerk dauerhaft verloren. Starte Netzwerk-Stack neu...")
    NET.restart()      # Startet nur das LAN/WLAN-Modul des SLZB neu, um die IP neu zu holen
    pingFailCount = 0  # Zähler zurücksetzen
    SLZB.delay(10000)  # 10 Sekunden warten, bis Verbindung wieder da ist
  end

  SLZB.delay(60000)  # Das Skript prüft den Zustand alle 60 Sekunden (Ressourcenschonend)
end