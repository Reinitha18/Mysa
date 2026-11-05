# Matrice de flux — réseau segmenté Mysa (GNS3)

Topologie : routeur pare-feu OpenWrt entre trois VLAN, relié à Internet par un nœud Cloud
(carte réseau de l'hôte).

| VLAN | Segment | Sous-réseau | Hôtes |
|---|---|---|---|
| 20 | Objets connectés | 192.168.20.0/24 | ESP32 `esp32-sec-01`, `esp32-cmf-01`, téléphone-caméra |
| 30 | Hub Mysa | 192.168.30.0/24 | hub (`192.168.30.20`) : broker, moteur, API/dashboard, caméra |
| 40 | Attaquant | 192.168.40.0/24 | VM Kali (lab d'intrusion) |
| — | WAN | DHCP (Cloud) | Internet (notifications, NTP) |

## Qui peut parler à qui

| Source | Destination | Port / protocole | Autorisé | Justification |
|---|---|---|---|---|
| Objets (ESP32) | Hub `192.168.30.20` | 8883/TCP (MQTT TLS) | ✅ | Seul canal de télémétrie et de commandes. Chiffré, authentifié, cloisonné par l'ACL du broker. |
| Objets (téléphone) | Hub `192.168.30.20` | 8000/TCP (HTTPS) | ✅ | Page caméra + WebSocket du flux vidéo (HTTPS obligatoire pour l'accès caméra dans Chrome). |
| Objets | Hub | tout autre port | ⛔ | Rien d'autre n'a de raison d'être : réduit la surface d'attaque d'un objet compromis. |
| Objets | Internet (WAN) | sortant | ✅* | NTP / DNS des objets. Désactivable pour un cloisonnement strict. |
| Objets | Attaquant | — | ⛔ | Aucun lien légitime. |
| Hub | Internet (WAN) | sortant | ✅ | Notifications (SMTP, CallMeBot) et mises à jour. |
| Hub | Objets | réponses MQTT | ✅ (suivi de connexion) | Les commandes transitent dans la connexion ouverte par l'objet vers le broker ; aucune connexion entrante nouvelle n'est nécessaire. |
| Hub | Attaquant | — | ⛔ | Aucun lien légitime. |
| Attaquant | Hub / Objets | — | ⛔ (par défaut) | **Isolé.** Débloqué règle par règle selon le test d'intrusion joué (TI-01 à TI-05), pour mesurer ce que le hub détecte dans chaque position. |
| Admin | Routeur (SSH/LuCI) | 22, 80, 443 | ✅ depuis le Hub seulement | Administration du pare-feu restreinte au segment du hub. |
| Tous les segments | Routeur | 53/DNS, 67-68/DHCP | ✅ | Adressage et résolution de noms. |

\* Flux optionnel : la règle `Objets → WAN` peut être retirée (`gns3/openwrt/firewall`) pour un
cloisonnement plus strict, au prix de la synchronisation d'heure des ESP32 par un autre moyen.

## Lecture sécurité (pour le mémoire)

- **Moindre privilège réseau** : un objet compromis (VLAN 20) ne peut parler qu'au broker du hub, et
  seulement en MQTT TLS. Il ne peut ni scanner le hub sur d'autres ports, ni atteindre les autres
  objets, ni l'attaquant. C'est la réponse réseau aux vulnérabilités V-01/V-02 (chapitre 4), en
  complément de l'ACL applicative du broker.
- **Double cloisonnement** : segmentation réseau (ce pare-feu) **et** ACL par compte sur le broker
  (`broker/acl.conf`). Même autorisé à joindre 8883, un objet n'écrit que sous ses propres topics.
- **Lab maîtrisé** : l'attaquant est isolé par défaut ; chaque scénario d'intrusion ouvre
  délibérément un seul chemin, ce qui rend les mesures « avant/après » du chapitre 9 reproductibles
  et interprétables (on sait exactement d'où vient l'attaque).
