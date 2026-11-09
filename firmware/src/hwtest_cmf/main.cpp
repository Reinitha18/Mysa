// Test matériel du nœud esp32-cmf-01 (confort), sans Wi-Fi ni MQTT
#include <Arduino.h>
/*#include <DHT.h>

const int DHT_PIN = 4, RELAY_PIN = 27;

DHT dht(DHT_PIN, DHT22);

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=== HWTEST esp32-cmf-01 ===");
  Serial.println("T1 Relais : ON 1 s puis OFF (clic audible)");
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);  delay(1000);
  digitalWrite(RELAY_PIN, HIGH); delay(500);
  dht.begin();
  Serial.println("T2 DHT22 : mesure toutes les 3 s");
}

void loop() {
  static unsigned long last = 0;
  if (millis() - last > 3000) {
    last = millis();
    float t = dht.readTemperature(), h = dht.readHumidity();
    if (isnan(t)) Serial.println("DHT22 : ECHEC de lecture");
    else Serial.printf("DHT22 : %.1f C  %.1f %%\n", t, h);
  }
}*/
#define RELAY_PIN 4




void setup() {
  Serial.begin(115200);

  // Initialiser le GPIO
  pinMode(RELAY_PIN, OUTPUT);

  Serial.println("=== TEST 2 : RELAIS MYSA ===");
}

void loop() {

  // ETAT 1
  digitalWrite(RELAY_PIN, LOW);
  Serial.println("GPIO = LOW (0V)");
  delay(3000);

  // ETAT 2
  digitalWrite(RELAY_PIN, HIGH);
  Serial.println("GPIO = HIGH (3.3V)");
  delay(3000);
}
