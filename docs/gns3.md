# Réseau segmenté Mysa dans GNS3 (Windows)

Ce guide monte la topologie réseau de Mysa dans GNS3 : un routeur pare-feu OpenWrt sépare trois
VLAN (objets, hub, attaquant), les ESP32 et le téléphone (Wi-Fi réels) entrent par un nœud Cloud
relié à la carte réseau de l'hôte. Fichiers fournis :

```
gns3/mysa.gns3            projet GNS3 à ouvrir (topologie, nœuds, liens)
gns3/openwrt/network      /etc/config/network  du routeur (VLAN 20/30/40 + WAN)
gns3/openwrt/dhcp         /etc/config/dhcp     (un pool par VLAN, hub en IP fixe .30.20)
gns3/openwrt/firewall     /etc/config/firewall (objets -> hub:8883/8000, attaquant isolé)
gns3/flux_matrix.md       matrice de flux (qui parle à qui, et pourquoi)
```

## Topologie

```
         Internet (box/hôte)
                │
            [Cloud WAN]
                │ e0 (DHCP)
        ┌───────────────────┐
        │ routeur pare-feu  │  OpenWrt — VLAN 20/30/40 sur le trunk e1
        │     (OpenWrt)     │
        └───────┬───────────┘
                │ e1 (trunk 802.1q)
          ┌─────────────┐
          │  sw-mysa    │  switch managé
          └──┬───┬───┬──┘
      vlan20 │   │vlan30 │vlan40
             │   │       │
     [Cloud objets]  [Cloud hub] [Cloud kali]
      (carte hôte)  (carte VM hub) (carte VM Kali)
     ESP32 + téléphone
```

| VLAN | Segment | Sous-réseau | Passerelle |
|---|---|---|---|
| 20 | Objets (ESP32, téléphone) | 192.168.20.0/24 | 192.168.20.1 |
| 30 | Hub Mysa (`192.168.30.20`) | 192.168.30.0/24 | 192.168.30.1 |
| 40 | Attaquant (Kali) | 192.168.40.0/24 | 192.168.40.1 |

## 1. Installer GNS3 + la GNS3 VM

1. Installer **GNS3** (Windows) depuis <https://www.gns3.com/software/download> (cocher les outils
   proposés : Wireshark, Npcap, etc.).
2. Installer la **GNS3 VM** (VMware Workstation Player, gratuit) : au premier lancement de GNS3,
   l'assistant *Setup Wizard* propose « Run appliances in a virtual machine » → importer la GNS3 VM
   (fichier `.ova` fourni par GNS3) dans VMware, puis la sélectionner dans GNS3.
   > La GNS3 VM est recommandée pour faire tourner l'appliance OpenWrt et relier des VM VMware.

## 2. Ouvrir le projet

GNS3 → **File → Open project** (ou *Import portable project*) → choisir `gns3/mysa.gns3`. La
topologie s'affiche avec ses six nœuds et leurs liens. Certains nœuds apparaîtront « non configurés » : c'est normal, on les lie aux
images/VM de ton poste aux étapes suivantes (les identifiants d'appliance sont propres à chaque
installation GNS3 et ne peuvent pas être livrés figés).

## 3. Lier le routeur OpenWrt

1. **Télécharger l'appliance OpenWrt** : GNS3 → *New template → Install an appliance from the GNS3
   Marketplace* → chercher **OpenWrt** → suivre l'assistant (télécharger l'image indiquée).
2. Sur le nœud `routeur-pare-feu` du projet : clic droit → *Change symbol/template* (ou supprimer le
   nœud et reposer une appliance OpenWrt au même endroit), en lui donnant **2 interfaces** :
   - `e0` → **Cloud WAN**
   - `e1` → **sw-mysa** (port trunk)
3. Démarrer le routeur, ouvrir sa console, et coller les configurations fournies :
   ```sh
   # dans la console OpenWrt, pour chaque fichier gns3/openwrt/* :
   # remplacer le contenu de /etc/config/network, /etc/config/dhcp, /etc/config/firewall
   vi /etc/config/network     # coller gns3/openwrt/network
   vi /etc/config/dhcp        # coller gns3/openwrt/dhcp
   vi /etc/config/firewall    # coller gns3/openwrt/firewall
   /etc/init.d/network restart
   /etc/init.d/firewall restart
   /etc/init.d/dnsmasq restart
   ```
   > Astuce : on peut aussi passer les fichiers par `scp`/`wget` depuis le hub, ou les coller via
   > LuCI (interface web, accessible depuis le VLAN hub une fois le réseau en place).

## 4. Relier le hub et l'attaquant (nœuds Cloud)

Le hub et Kali sont des **nœuds Cloud** reliés chacun à une carte réseau de l'hôte. Le projet ne
contient volontairement **aucun nœud VMware** : un nœud VMware doit pointer vers le fichier `.vmx`
d'une VM, propre à chaque poste, et GNS3 refuse d'importer un projet où ce chemin est vide
(erreur « JSON schema error … 'vmx_path': '' is too short »).

1. Dans VMware, mettre la carte réseau de chaque VM sur un **réseau hôte dédié** : par exemple
   `VMnet2` pour la VM du hub, `VMnet3` pour la VM Kali (*Edit → Virtual Network Editor*, mode
   *Host-only*, **DHCP de VMware désactivé** : c'est OpenWrt qui distribue les adresses).
2. Dans GNS3, clic droit sur `hub-mysa (Cloud -> VM hub)` → *Configure* → *Ethernet interfaces* →
   cocher *Show special Ethernet interfaces* → ajouter `VMnet2` (ou la carte où tourne Docker si le
   hub est le PC Windows lui-même). Interface sur le **VLAN 30** ; donner au hub l'IP `192.168.30.20`
   (réservation DHCP déjà prévue dans `gns3/openwrt/dhcp`, adapter la MAC).
3. Même chose pour `kali (Cloud -> VM Kali)` avec `VMnet3`, interface sur le **VLAN 40**
   (voir docs/kali.md).

> Alternative : si tu préfères des nœuds VMware, supprime le nœud Cloud, crée un modèle VMware
> (*Edit → Preferences → VMware VMs → New*, choisir la VM) et pose-le au même endroit avec le même lien.

## 5. Faire entrer les ESP32 et le téléphone (nœud Cloud)

Le nœud **objets (Cloud)** relie le VLAN 20 à une **carte réseau de l'hôte**. Clic droit →
*Configure* → onglet *Ethernet interfaces* → choisir la carte reliée à la box/au réseau des objets.

> Le pont **Wi-Fi** vers GNS3 est peu fiable sous Windows (voir « Limites » du document de
> livrables). Préférer une **carte Ethernet** (ou un câble vers la box) pour faire entrer les ESP32
> et le téléphone dans la topologie.

## 6. Vérifier

1. Démarrer tous les nœuds (bouton ▶). Le routeur distribue les adresses (DHCP par VLAN).
2. Depuis le hub (`192.168.30.20`), vérifier qu'on joint le broker et que les ESP32 publient
   (dashboard `https://192.168.30.20:8000/dashboard/`).
3. Tester la segmentation (doit correspondre à `gns3/flux_matrix.md`) :
   - un objet (VLAN 20) joint le hub sur **8883** et **8000**, mais rien d'autre ;
   - la VM Kali (VLAN 40) ne joint **rien** tant qu'on n'a pas décommenté la règle du scénario
     d'attaque dans `gns3/openwrt/firewall` (puis `/etc/init.d/firewall restart`).

## En cas de souci

- **Le projet ne s'ouvre pas sur ta version de GNS3** : recréer la topologie du §Topologie à la main
  (5 nœuds, 5 liens) prend quelques minutes ; les configurations du routeur et la matrice de flux
  restent valables telles quelles.
- **Pas d'adresse sur un VLAN** : vérifier le mapping des ports du switch (trunk vers le routeur,
  accès pour les hôtes) et le redémarrage de `network`/`dnsmasq` sur OpenWrt.
- **Les objets ne joignent pas le hub** : vérifier l'IP fixe du hub (`192.168.30.20`), les règles du
  pare-feu (`Objets-vers-Hub-MQTT`/`-HTTPS`) et le pare-feu Windows de la VM hub (ports 8883/8000).
