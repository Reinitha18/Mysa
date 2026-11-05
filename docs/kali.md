# VM Kali du lab d'attaque (import VMware + réseau GNS3)

Plutôt qu'une VM de plusieurs gigaoctets livrée toute faite, on part de l'**image VMware officielle
de Kali** (prête à importer) et un **script** installe le lab en une commande. C'est plus léger,
reproductible, et toujours à jour.

> ⚠️ Lab d'intrusion sur **ton** prototype, réseau **isolé**. Voir `attack-lab/README.md`.

## 1. Télécharger l'image Kali pour VMware

1. Aller sur <https://www.kali.org/get-kali/#kali-virtual-machines>.
2. Onglet **VMware**, télécharger l'archive **7z** (ex. `kali-linux-20xx.x-vmware-amd64.7z`).
3. Décompresser (7-Zip) : on obtient un dossier avec un fichier `.vmx` et des disques `.vmdk`.

## 2. Importer dans VMware

1. Ouvrir **VMware Workstation Player/Pro** → *Open a Virtual Machine* → choisir le `.vmx`.
2. Démarrer la VM. Identifiants par défaut : `kali` / `kali`. Faire les mises à jour :
   ```bash
   sudo apt update && sudo apt -y full-upgrade
   ```

## 3. Rattacher la VM au réseau GNS3 (VLAN 40)

Deux manières de relier la VM Kali à la topologie GNS3 (voir `docs/gns3.md`) :

- **Nœud VMware dans GNS3** (recommandé si la GNS3 VM tourne sous VMware) : dans GNS3, le nœud
  `kali` du projet se lie à cette VM (clic droit → *Configure* → choisir la VM). GNS3 gère alors le
  câblage vers le switch, sur le port **VLAN 40**.
- **Réseau VMware segmenté** : à défaut, mettre l'adaptateur réseau de la VM sur un *LAN segment*
  VMware dédié, lui-même relié au VLAN 40 via un nœud Cloud dans GNS3.

Vérifier que Kali obtient une adresse du VLAN 40 (`192.168.40.0/24`, passerelle `192.168.40.1`) :
```bash
ip a ; ip route
```

## 4. Installer le lab

Copier le dossier `attack-lab/` (et le dépôt) sur la VM, puis :
```bash
bash attack-lab/install.sh
```
Copier enfin le certificat de la CA Mysa (`broker/certs/ca.crt` du hub) sur la VM et renseigner
`attack-lab/lab.env` (`CA_CERT`, `TARGET_HOST=192.168.30.20`, identifiants).

## 5. Lancer les attaques

```bash
set -a; source attack-lab/lab.env; set +a
python3 attack-lab/run_report.py --out attack-lab/report.md
```

Rappel de segmentation : par défaut, le pare-feu GNS3 **isole** la VLAN 40. Pour qu'un scénario
atteigne le hub, décommenter la règle correspondante dans `gns3/openwrt/firewall` puis
`/etc/init.d/firewall restart` (c'est ce qui rend les mesures « avant/après » interprétables : on
sait exactement quel chemin on a ouvert).

## Ce qui dépend de toi

- Télécharger et importer l'image Kali.
- Rattacher la VM au VLAN 40 et copier `ca.crt`.
- Lancer les attaques pendant les essais et la démonstration.
