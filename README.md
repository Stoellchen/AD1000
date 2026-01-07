Hi

I like to share my setup with you. I'm doing homeautomation since long time. Started with misterhouse (https://misterhouse.sourceforge.net/) mostly in pearl. I've made many things wiht X10, iButton und much more.

Now after several years with Raspberry PI 4 and 5 I moved to a more reliable setup. I never found an easy way to restore everything with one touch with all the special stuff I did.

I now have 4x gmktec g3 plus and one big machine.
- gmktec have 16GB and 1TB NVMe
  - 3 normal nodes and one proxmox backup 
- big one: 128GB RAM and 6x20TB ZFS 4TB cache
    - Jonsbo N5 Chassis
    - AsRock Z790 Pro RS
    - i5 with VT
    - 7x 20GB Toshiba MG10 Series - 1 Spare
    - Samsung 990 Pro mit Heatsink
    - 2x 64 GB (2x 32 GB) DDR5 5600 CL46 Crucial Pro 2er Kit
    - 4 Silent fan's (Noctua)
    - Seasonic PRIME Fanless TX 700
    - Intel X550T2 (10GB RJ45) - for later
==> everyhing is running on proxmox with LXC or VMs

VMs:
Node 1:
  -  Home Assistant / VM
      - Disk:    64 GB
      - RAM:     2-15 GB
      - CPU:     4
  -  Postgres for recorder and history
      - Disk:    10 GB
      - RAM:     1 GB
      - CPU:     1
  -  Zigbee2mqtt
      - Disk:    5 GB
      - RAM:     1 GB
      - CPU:     2
  -  emqx
      - Disk:    4 GB
      - RAM:     1 GB
      - CPU:     2


Node 2:
  -  Prometheus
      - Disk:    4 GB
      - RAM:     512 MB
      - CPU:     1
  -  Lyrion
      - Disk:    3 GB
      - RAM:     512 MB
      - CPU:     1
  -  Smokeping
      - Disk:    2 GB
      - RAM:     256 MB
      - CPU:     1


Node 3:
  -  Myspeed
      - Disk:    4 GB
      - RAM:     512 MB
      - CPU:     1
  -  Uptime Kuma
      - Disk:    4 GB
      - RAM:     512 MB
      - CPU:     1
  -  Conertix
      - Disk:    20 GB
      - RAM:     512 MB - increased if needed
      - CPU:     2
  -  My IP
      - Disk:    4 GB
      - RAM:     256 MB
      - CPU:     1


Node 4:
    -  Proxmox PBS


Node 5:
  -  Tautulli
      - Disk:    10 GB
      - RAM:     512 MB
      - CPU:     1
  -  ESPHome
      - Disk:    10 GB
      - RAM:     512 MB - increased if needed
      - CPU:     2  - increased if needed
 -  Grafana
      - Disk:    2 GB
      - RAM:     512 MB
      - CPU:     1
  -  Plex / VM
      - Disk:    60 GB
      - RAM:     32 GB
      - CPU:     3
  -  sabnzbd (radarr, sonarr, observeerr, sabnzbd) / VM
      - Disk:    100 GB
      - RAM:     40 GB
      - CPU:     4
  -  Influx - longterm DB filled from HA / VM
      - Disk:    15 GB
      - RAM:     80 GB
      - CPU:     1
  -  Mailrelay / VM
      - Disk:    20 GB
      - RAM:     1 GB
      - CPU:     1
       
Others:
  -  SLZB-MR4U Zigbee Coordinator & Matter over Thread
    - It works perfectly. I had problems in the beginning, but with the new Setup/HA-Version 👍


Backups I do - or better the system:
  -  Everything is mirrored to the other nodes
  -  Everything has local backups and to the Proxmox PBS
  -  Compression rate at the moment after 14 Days: 60% on the PBS-ZFS
      - I have to watch and maybe I need to keep lower backups of the machines, but at the moment it looks good
      - Optional I can add an external USB-Drive as backup-destination for the longer backups I want to keep
  -  github: I was unable to upload the app-deamon-apps directly - didn't find a solution. I have to move it by hand, but they are mostly static. If you look for another circadian solution, you'll find something in my __appdaemon-mirror/apps directory
         

HA Backups:
  -  directly on the mounted ZFS-NFS-Store
  -  google drive with Add-On
  -  Snapshots

Medien
  -  directly on the ZFS-NFS-Store

