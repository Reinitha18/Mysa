# Plan de la maquette Mysa

Schéma : **`docs/plan_maquette.svg`** (vue de dessus). Ce document précise dimensions, placement et
fixations.

## Support

- **Planche** : contreplaqué (ou carton rigide type Forex) d'environ **80 × 50 cm**, épaisseur 5 mm
  minimum pour visser les cartes.
- Deux zones délimitées au feutre/adhésif : **Entrée** (gauche) et **Salon** (droite).

## Zone Entrée (nœud ESP32 « sec-01 »)

| Élément | Position | Hauteur / orientation | Fixation |
|---|---|---|---|
| Lecteur RFID RC522 | bord gauche, haut | à hauteur de main (badge présenté à plat) | vis + entretoises nylon |
| Serrure (servo SG90) | à droite du lecteur | pêne factice en carton/bois | équerre + vis ; **servo alimenté à part** |
| PIR HC-SR501 | sous le lecteur | lentille orientée vers l'entrée (~110°) | double-face mousse |
| Buzzer + LED | à droite du PIR | visibles/audibles de face | double-face |
| Carte ESP32 sec-01 | bas de zone | boîtier ouvert pour la démo | vis + entretoises |

## Zone Salon (nœud ESP32 « cmf-01 »)

| Élément | Position | Remarque | Fixation |
|---|---|---|---|
| Lampe (relais) | bord gauche, haut | ampoule **basse tension** pour la maquette | support + colliers |
| DHT22 | bord droit, haut | éloigné de la lampe (éviter la chaleur parasite) | double-face / clip |
| Carte ESP32 cmf-01 | bas de zone | **relais câblé en basse tension** (sécurité) | vis + entretoises |

## Téléphone-caméra

- **Emplacement** : au centre-droit, sur un **support réglable** (trépied de table ou bras),
  orienté pour couvrir **à la fois l'entrée et le salon**.
- Se connecte au hub en Wi-Fi ; ouvre `https://<hub>:8000/camera/` dans Chrome (HTTPS, voir
  `docs/https.md`).

## Alimentation

- **Deux alimentations 5 V** séparées (une par nœud) ; le **servo** de la serrure sur une sortie
  dédiée (pointes de courant) pour ne pas faire redémarrer l'ESP32.
- Barrette multiprise unique pour couper tout d'un coup en fin de démo.

## Câblage (rappels)

- RC522 : corriger le lecteur (répond `0x00`) et ajouter le servo — **câblage matériel (toi)**,
  voir le firmware `firmware/esp32-sec-01`.
- Séparer les masses signal/puissance ; colliers pour maintenir les câbles à plat.

## Liste de courses (maquette)

Planche + équerres, entretoises nylon M3, vis, double-face mousse, colliers, support de téléphone,
ampoule basse tension + douille, 2 alimentations 5 V, multiprise.
