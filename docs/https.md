# HTTPS du hub (obligatoire pour la caméra du téléphone)

Chrome n'autorise l'accès à la caméra (`getUserMedia`) que sur une **origine sécurisée** : HTTPS,
ou `localhost`. La page caméra (`/camera/`) s'ouvre donc en **HTTPS** sur le hub. On signe le
certificat du hub avec la **CA privée de Mysa**, qu'on installe sur le téléphone : plus d'avertissement
de sécurité, et la même CA sert déjà au broker MQTT (TLS 8883).

## 1. Générer la CA et le certificat du hub

Sur la VM hub, à la racine du dépôt :

```bash
scripts/gen_certs.sh 192.168.50.20 mysa-hub
#                     ^ IP du hub   ^ nom d'hôte
```

Cela crée dans `broker/certs/` :

| Fichier | Rôle | Partagé ? |
|---|---|---|
| `ca.crt` | autorité de certification Mysa | à installer sur le téléphone et les postes |
| `ca.key` | clé privée de la CA | **jamais** (reste sur le hub) |
| `server.crt` / `server.key` | certificat du hub (SAN : `mysa-hub` + IP) | non |

Le certificat couvre `mysa-hub`, `localhost`, l'IP du hub et `127.0.0.1` (champ *SubjectAltName*,
exigé par les navigateurs). La CA est réutilisée si elle existe déjà ; seul le certificat serveur est
regénéré.

> Donne une **IP fixe** au hub (réservation DHCP) et, idéalement, fais résoudre `mysa-hub` vers cette
> IP (fichier hosts du poste, ou DNS de la box) pour ouvrir `https://mysa-hub:8000/` sans retenir l'IP.

## 2. Lancer le hub en HTTPS

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile broker/certs/server.key \
  --ssl-certfile broker/certs/server.crt
```

Le dashboard est alors sur `https://mysa-hub:8000/dashboard/` et la page caméra sur
`https://mysa-hub:8000/camera/`. Les WebSockets passent automatiquement en `wss://` (même origine).

> En production sur Windows, c'est le `docker-compose` du hub qui lancera uvicorn avec ces options
> (livrable du dimanche) ; la commande ci-dessus sert à vérifier en développement.

## 3. Installer la CA Mysa sur le téléphone Android

1. Copier `broker/certs/ca.crt` sur le téléphone (câble USB, e-mail à soi, clé USB…).
2. **Paramètres → Sécurité → Chiffrement et identifiants → Installer un certificat → Certificat CA**
   (le libellé varie selon la version d'Android), choisir le fichier `ca.crt`.
3. Android prévient qu'un tiers pourra inspecter le trafic : c'est normal pour une CA privée ;
   confirmer. La CA « Mysa Root CA » apparaît dans les certificats de l'utilisateur.

Sur un poste (pour le dashboard sans avertissement) : importer `ca.crt` dans les autorités de
confiance du navigateur ou du système.

## 4. Vérifier

Si le hub est protégé par mot de passe (`MYSA_DASHBOARD_PASSWORD`), se connecter d'abord au dashboard
depuis le téléphone : la session vaut aussi pour la page caméra.

Sur le téléphone, ouvrir **`https://mysa-hub:8000/camera/`** dans Chrome :

- pas d'avertissement de certificat (CA installée) ;
- le bouton **« Démarrer »** demande l'autorisation caméra, puis l'aperçu s'affiche ;
- le point passe au vert (« connecté ») et le compteur d'images augmente ;
- sur le dashboard (`/dashboard/`), le panneau **« Caméra en direct »** affiche le flux, et un
  mouvement devant la caméra crée une alerte (topic `home/cam-01/motion`).

## Ce qui dépend de toi

- Installer `ca.crt` sur le téléphone et les postes.
- Donner une IP fixe au hub (et éventuellement résoudre `mysa-hub`).
- Autoriser l'accès caméra dans Chrome au premier lancement.
