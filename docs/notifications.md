# Notifications Mysa (e-mail et SMS)

Mysa prévient l'occupant pour les **alertes critiques seulement** : toute alerte de gravité
**« high »** (alarme déclenchée, intrusion détectée par corrélation, lecteur de badges bloqué,
surchauffe, valeur hors contrat…) et tout **nœud passé hors ligne** (Last Will MQTT). Les alertes
moyennes et faibles (par ex. quelques badges refusés) restent visibles dans le dashboard, sans
notification. Une seule notification est envoyée **par épisode**, pour ne pas inonder.

Les deux canaux sont **gratuits** et **facultatifs** : un canal dont les variables ne sont pas
renseignées est simplement ignoré. Tout se configure dans le fichier `.env` (voir `.env.example`).
Pour tout couper d'un coup : `MYSA_NOTIFY=0`.

Le code vit dans `engine/notify.py` et n'utilise que la bibliothèque standard (aucune dépendance en
plus). Il est branché sur le moteur au démarrage ; aucune action n'est requise côté code.

---

## 1. E-mail — SMTP (Gmail avec mot de passe d'application)

Gmail n'accepte pas le mot de passe habituel du compte pour un programme : il faut un **mot de passe
d'application** (16 caractères), gratuit, qui nécessite la validation en deux étapes.

1. Activer la **validation en deux étapes** : <https://myaccount.google.com/signinoptions/twosv>.
2. Créer un mot de passe d'application : <https://myaccount.google.com/apppasswords> → nommer
   « Mysa » → copier les 16 caractères.
3. Renseigner `.env` :
   ```
   MYSA_SMTP_HOST=smtp.gmail.com
   MYSA_SMTP_PORT=587
   MYSA_SMTP_USER=ton.adresse@gmail.com
   MYSA_SMTP_PASSWORD=les16caracteres
   MYSA_SMTP_FROM=ton.adresse@gmail.com      # facultatif (par défaut = USER)
   MYSA_SMTP_TO=destinataire@exemple.com      # plusieurs adresses possibles, séparées par des virgules
   ```

> Port 587 = STARTTLS (recommandé). Port 465 = SSL (le code bascule automatiquement). D'autres
> fournisseurs (Outlook, OVH, Infomaniak…) fonctionnent de la même façon : changer `HOST`/`PORT`.

---

## 2. SMS — passerelle open source sur un téléphone Android

Principe : un **téléphone Android** avec une carte SIM fait office de passerelle. Une application
open source expose une petite **API HTTP** sur le réseau local ; Mysa lui envoie le texte, le
téléphone l'envoie en SMS **avec le forfait de la SIM** (aucun service payant).

Application recommandée : **android-sms-gateway** (capcom6), gratuite et open source
(<https://github.com/capcom6/android-sms-gateway>), en **mode local** (le téléphone reste sur le
réseau de la maison, rien ne sort vers un cloud).

1. Installer l'application sur le téléphone passerelle, choisir le **mode local**, autoriser l'envoi
   de SMS.
2. Noter l'**adresse IP** du téléphone, le **port** (8080 par défaut), et les **identifiants**
   (utilisateur/mot de passe) affichés par l'application.
3. Donner au téléphone une **IP fixe** (réservation DHCP sur la box/routeur) pour que l'adresse ne
   change pas.
4. Renseigner `.env` :
   ```
   MYSA_SMS_URL=http://192.168.50.40:8080/message   # IP du téléphone passerelle
   MYSA_SMS_USER=sms                                  # identifiant affiché par l'application
   MYSA_SMS_PASSWORD=motdepasse
   MYSA_SMS_TO=+261340000000                          # numéro(s) destinataire(s), séparés par des virgules
   ```

> Mysa envoie `POST {"message": "...", "phoneNumbers": ["..."]}` avec authentification basique, qui
> est le format de cette application. Une autre passerelle à l'API différente demanderait d'adapter
> `send_sms` dans `engine/notify.py`.

---

## 3. Vérifier que tout marche

Après avoir renseigné `.env`, tester un canal sans lancer tout le moteur :

```bash
python - <<'PY'
from dotenv import load_dotenv; load_dotenv()
from engine import notify
print("Canaux ayant accepté l'envoi :", notify.dispatch(
    "esp32-sec-01", "Test de notification Mysa", "high", "rule"))
PY
```

La liste affichée contient le nom de chaque canal configuré et joignable (`e-mail`, `SMS`). Un canal absent de la liste est soit non renseigné, soit injoignable : le détail de
l'erreur apparaît dans les journaux du moteur (niveau `WARNING`).

En fonctionnement, les notifications partent toutes seules dès qu'une alerte « high » ou un passage
hors ligne est enregistré — l'envoi se fait dans un thread séparé, sans jamais ralentir l'ingestion.

## Ce qui dépend de toi (hors logiciel)

- Créer le mot de passe d'application Gmail.
- Installer l'application SMS sur un téléphone Android et lui donner une IP fixe.
- Fournir le forfait SMS de la carte SIM du téléphone passerelle.
