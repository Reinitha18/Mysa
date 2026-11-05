// include/mysa_net.h -- Wi-Fi + MQTT/TLS communs aux deux nœuds
//
// Le réseau tourne dans sa propre tâche FreeRTOS : la logique locale du nœud (serrure,
// RFID, alarme, thermostat) ne bloque jamais, même broker ou Wi-Fi absents.
//  - publications : publishSensor()/publishEvent() déposent le message dans une file,
//    vidée par la tâche réseau dès que la connexion est établie ;
//  - commandes : reçues par la tâche réseau, récupérées dans loop() par pollCommand() ;
//  - présence : Last Will retenu home/<id>/status = "offline", "online" à la connexion ;
//  - session persistante + abonnement QoS 1 : une commande envoyée pendant une coupure
//    est délivrée à la reconnexion.
#pragma once
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include "mysa_config.h"   // généré à la compilation (firmware/scripts/gen_config.py)

struct MysaMsg { char topic[64]; char payload[200]; };
struct MysaCmd { char act[24]; char value[40]; };

static WiFiClientSecure net;
static PubSubClient mqtt(net);
static QueueHandle_t outQ, cmdQ;
static volatile bool netUp = false;
static char statusTopic[48];

// Extrait le dernier segment du topic (home/<id>/cmd/<act> -> <act>)
inline const char* lastSegment(const char* topic) {
  const char* p = strrchr(topic, '/');
  return p ? p + 1 : topic;
}

static void onMqttMessage(char* topic, byte* payload, unsigned int len) {
  MysaCmd c{};
  strlcpy(c.act, lastSegment(topic), sizeof(c.act));
  unsigned int n = len < sizeof(c.value) - 1 ? len : sizeof(c.value) - 1;
  memcpy(c.value, payload, n);
  c.value[n] = 0;
  xQueueSend(cmdQ, &c, 0);
}

static bool tryConnect() {
  static unsigned long lastWifi = 0, lastMqtt = 0;
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastWifi > 10000 || lastWifi == 0) {
      lastWifi = millis();
      Serial.printf("[WiFi] Connexion a %s\n", WIFI_SSID);
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASS);
    }
    return false;
  }
  if (mqtt.connected()) return true;
  if (millis() - lastMqtt < 5000 && lastMqtt != 0) return false;
  lastMqtt = millis();
  Serial.printf("[WiFi] OK IP=%s RSSI=%d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  Serial.printf("[MQTT] Connexion TLS a %s:%d ... ", MQTT_HOST, MQTT_PORT);
  // cleanSession=false : le broker garde l'abonnement et les commandes QoS 1 en attente
  if (mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASS, statusTopic, 1, true, "offline", false)) {
    Serial.println("OK");
    char t[64];
    snprintf(t, sizeof(t), "home/%s/cmd/#", DEVICE_ID);
    mqtt.subscribe(t, 1);
    mqtt.publish(statusTopic, "online", true);
    return true;
  }
  // rc=-2 : TCP/TLS refusé (IP, port, certificat) ; rc=4/5 : identifiants/ACL
  Serial.printf("echec rc=%d\n", mqtt.state());
  char err[100];
  if (net.lastError(err, sizeof(err))) Serial.printf("       TLS: %s\n", err);
  return false;
}

static void netTask(void*) {
  MysaMsg m;
  bool pending = false;
  for (;;) {
    netUp = tryConnect();
    if (netUp) {
      mqtt.loop();
      // Un message en échec reste en tête et sera renvoyé après reconnexion
      while (pending || xQueueReceive(outQ, &m, 0) == pdTRUE) {
        pending = !mqtt.publish(m.topic, m.payload);
        if (pending) break;
      }
    }
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

inline void setupNet() {
  outQ = xQueueCreate(40, sizeof(MysaMsg));
  cmdQ = xQueueCreate(8, sizeof(MysaCmd));
  snprintf(statusTopic, sizeof(statusTopic), "home/%s/status", DEVICE_ID);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  net.setCACert(CA_CERT);
  net.setHandshakeTimeout(5);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(15);
  mqtt.setSocketTimeout(5);
  xTaskCreatePinnedToCore(netTask, "mysa-net", 8192, nullptr, 1, nullptr, 0);
}

inline bool netConnected() { return netUp; }

inline bool pollCommand(MysaCmd& c) {
  if (xQueueReceive(cmdQ, &c, 0) != pdTRUE) return false;
  for (char* p = c.value; *p; p++) *p = tolower(*p);
  // espaces de début/fin
  char* s = c.value; while (*s == ' ') s++;
  memmove(c.value, s, strlen(s) + 1);
  for (int i = strlen(c.value) - 1; i >= 0 && c.value[i] == ' '; i--) c.value[i] = 0;
  Serial.printf("[CMD] %s = %s\n", c.act, c.value);
  return true;
}

static bool enqueue(const char* sensor, const char* payload) {
  MysaMsg m;
  snprintf(m.topic, sizeof(m.topic), "home/%s/%s", DEVICE_ID, sensor);
  strlcpy(m.payload, payload, sizeof(m.payload));
  bool ok = xQueueSend(outQ, &m, 0) == pdTRUE;   // file pleine (longue coupure) : message perdu
  Serial.printf("[PUB] %s %s %s\n", ok ? "ok " : "PLEIN", m.topic, m.payload);
  return ok;
}

// Publie {"device_id","sensor","value","unit"} sur home/<id>/<sensor>
inline bool publishSensor(const char* sensor, float value, const char* unit) {
  char payload[200];
  snprintf(payload, sizeof(payload),
           "{\"device_id\":\"%s\",\"sensor\":\"%s\",\"value\":%.2f,\"unit\":\"%s\"}",
           DEVICE_ID, sensor, value, unit);
  return enqueue(sensor, payload);
}

// Variante avec un champ texte supplémentaire (ex. "uid" d'un badge)
inline bool publishEvent(const char* sensor, float value, const char* unit, const char* key, const char* text) {
  char payload[200];
  snprintf(payload, sizeof(payload),
           "{\"device_id\":\"%s\",\"sensor\":\"%s\",\"value\":%.2f,\"unit\":\"%s\",\"%s\":\"%s\"}",
           DEVICE_ID, sensor, value, unit, key, text);
  return enqueue(sensor, payload);
}
