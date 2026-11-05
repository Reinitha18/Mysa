# Mysa — fiche produit

**La sécurité comportementale pour la maison connectée, qui apprend ce qui est normal chez vous.**

## En une phrase

Mysa est un **hub de cybersécurité domestique** qui surveille les objets connectés de la maison,
apprend leur comportement habituel et **alerte en cas d'anomalie** — intrusion, capteur manipulé,
appareil muet — sans envoyer vos données dans le cloud.

## Le problème

Les maisons intelligentes multiplient les objets connectés souvent **mal sécurisés** : trafic en
clair, mots de passe par défaut, aucune surveillance. Un objet compromis devient une porte d'entrée,
et l'occupant ne s'en aperçoit pas.

## La solution Mysa

Un petit **hub local** (un mini-PC ou une box) qui :

- **chiffre et authentifie** tous les échanges (MQTT TLS, comptes et droits par appareil) ;
- **apprend le comportement normal** de chaque capteur et repère ce qui en sort (valeurs aberrantes,
  rythme anormal, dérive, combinaisons inhabituelles) ;
- **corrèle plusieurs capteurs** : mouvement alors que l'alarme est armée et sans badge, présence
  confirmée par la caméra et le détecteur, accès à une heure inhabituelle ;
- **prévient gratuitement** par e-mail ou SMS, pour les alertes critiques ;
- affiche tout dans un **tableau de bord clair**, en langage d'occupant, avec acquittement des alertes.

## Points forts

| | |
|---|---|
| 🔒 **Données chez vous** | Tout reste sur le hub local ; aucun abonnement cloud obligatoire. |
| 🧠 **Apprentissage, pas de règles figées** | S'adapte à votre foyer ; moins d'une fausse alerte par jour (mesuré). |
| 🧩 **Explicable** | Chaque alerte dit *pourquoi* (règle claire ou comportement inhabituel). |
| 📷 **Caméra sans appli** | Un vieux téléphone Android devient caméra via une simple page web. |
| 💸 **Notifications gratuites** | E-mail et SMS (via un téléphone), alertes critiques seulement — sans frais récurrents. |
| 🛡️ **Défense en profondeur** | Chiffrement, droits par appareil, détection comportementale, réseau segmenté. |
| 🧪 **Éprouvé** | Lab d'attaque intégré (TI-01..05) et tests automatisés. |

## Pour qui

- **Madagascar** : adapté aux contraintes locales — fonctionne **hors ligne**, notifications par SMS
  (carte SIM), matériel abordable (ESP32, téléphone recyclé), installation simple en une commande.
- **International** : hub reproductible (Docker), standards ouverts (MQTT, TLS), extensible à d'autres
  capteurs et intégrable à un réseau segmenté.

## Comment ça marche (vue d'ensemble)

```
Objets connectés  →  Broker MQTT (TLS)  →  Moteur (apprentissage + règles + corrélation)
(ESP32, téléphone)                              │
                                                ├─ Tableau de bord web
                                                └─ Notifications (e-mail / SMS)
```

Schéma détaillé : `docs/architecture.svg`.

## Contenu d'un déploiement

- 2 nœuds **ESP32** (sécurité & accès, confort) — PIR, RFID, serrure, DHT22, relais.
- **Hub** logiciel (Docker) : broker, moteur, API, tableau de bord, pont caméra.
- **Téléphone** recyclé en caméra.
- Réseau **segmenté** (VLAN objets / hub / administration) avec pare-feu.

## Caractéristiques techniques

- MQTT sur TLS 1.2+, authentification et ACL par appareil.
- Détection : 4 détecteurs comportementaux + règles explicables + corrélation multi-capteurs.
- Déploiement : `docker compose` (Windows/Linux), HTTPS, certificats d'une CA privée.
- Open source, documenté, testé (59 tests automatisés).

---

_Mysa — projet de fin d'études. Prototype de recherche ; déploiement réel après durcissement et
validation sur site._
