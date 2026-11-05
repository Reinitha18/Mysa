// esp32-cmf-01 : confort (DHT22, relais pour lampe ou prise)
//
// Le relais a deux modes, gardés en NVS :
//  - manual : piloté par les commandes relay on/off (dashboard, automatisations du hub) ;
//  - auto   : thermostat local (ventilateur) -- relais ON au-dessus de la consigne,
//             OFF sous consigne - HYSTERESIS ; fonctionne sans hub.
#include <Arduino.h>
#include <DHT.h>
#include <Preferences.h>
#include "mysa_net.h"

const int DHT_PIN   = 4;
const int RELAY_PIN = 27;
const bool RELAY_ACTIVE_LOW = true;   // la plupart des modules 1 canal

const unsigned long PERIOD_MS = 5000;        // le DHT22 ne supporte pas < 2 s
const float HYSTERESIS = 0.5;

DHT dht(DHT_PIN, DHT22);
Preferences prefs;
bool relayOn = false, autoMode = false;
float setpoint = 28.0;

void setRelay(bool on) {
  relayOn = on;
  digitalWrite(RELAY_PIN, (on ^ RELAY_ACTIVE_LOW) ? HIGH : LOW);
}
void publishStates() {           // état complet, à chaque (re)connexion
  publishSensor("relay", relayOn, "bool");
  publishSensor("relay_auto", autoMode, "bool");
  publishSensor("setpoint", setpoint, "C");
}

void handleCommand(const MysaCmd& c) {
  bool on = !strcmp(c.value, "on") || !strcmp(c.value, "1");
  if (!strcmp(c.act, "relay")) {
    autoMode = false;                       // une commande manuelle reprend la main
    prefs.putBool("auto", false);
    setRelay(on);
    publishStates();
  } else if (!strcmp(c.act, "mode")) {
    autoMode = !strcmp(c.value, "auto");
    prefs.putBool("auto", autoMode);
    publishStates();
  } else if (!strcmp(c.act, "setpoint")) {
    float v = atof(c.value);
    if (v >= 10 && v <= 40) { setpoint = v; prefs.putFloat("setpoint", v); }
    publishStates();
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n=== Mysa esp32-cmf-01 (confort) ===");
  pinMode(RELAY_PIN, OUTPUT);
  setRelay(false);
  prefs.begin("mysa", false);
  autoMode = prefs.getBool("auto", false);
  setpoint = prefs.getFloat("setpoint", 28.0);
  dht.begin();
  setupNet();
}

void loop() {
  static bool wasUp = false;
  bool up = netConnected();
  if (up && !wasUp) publishStates();
  wasUp = up;

  MysaCmd c;
  while (pollCommand(c)) handleCommand(c);

  static unsigned long last = 0;
  if (millis() - last >= PERIOD_MS) {
    last = millis();
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (isnan(t) || isnan(h)) {
      Serial.println("[DHT] lecture invalide (cablage / pull-up ?)");
      publishSensor("dht_error", 1, "bool");
    } else {
      publishSensor("temperature", t, "C");
      publishSensor("humidity", h, "%");
      if (autoMode) {
        if (!relayOn && t > setpoint) setRelay(true);
        else if (relayOn && t < setpoint - HYSTERESIS) setRelay(false);
      }
    }
    publishSensor("relay", relayOn, "bool");
  }
  delay(10);
}
