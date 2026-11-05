// Test matériel du nœud esp32-sec-01 (sécurité & accès), sans Wi-Fi ni MQTT
#include <Arduino.h>
#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>

const int PIR_PIN = 13, DOOR_PIN = 14, BUZZER_PIN = 25, LED_PIN = 26, SERVO_PIN = 27, SS_PIN = 5, RST_PIN = 22;
const bool DOOR_IS_BUTTON = false;   // bouton : appui = ouverte ; false pour un contact MC-38

MFRC522 rfid(SS_PIN, RST_PIN);
Servo servo;

void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(PIR_PIN, INPUT);
  pinMode(DOOR_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  Serial.println("\n=== HWTEST esp32-sec-01 ===");
  Serial.println("T1 LED : 3 clignotements");
  for (int i = 0; i < 3; i++) { digitalWrite(LED_PIN, HIGH); delay(300); digitalWrite(LED_PIN, LOW); delay(300); }
  Serial.println("T2 Buzzer : 2 bips");
  for (int i = 0; i < 2; i++) { digitalWrite(BUZZER_PIN, HIGH); delay(150); digitalWrite(BUZZER_PIN, LOW); delay(200); }
  Serial.println("T3 Servo : 0 -> 90 -> 0 degres");
  servo.setPeriodHertz(50);
  servo.attach(SERVO_PIN, 500, 2400);
  servo.write(0); delay(700); servo.write(90); delay(700); servo.write(0); delay(700);
  SPI.begin();
  rfid.PCD_Init();
  byte v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.printf("T4 RC522 : VersionReg = 0x%02X -> %s\n", v,
                (v == 0x91 || v == 0x92) ? "OK" : (v == 0x00 || v == 0xFF) ? "ECHEC (cablage SPI / 3.3V)" : "clone, probablement OK");
  Serial.println("T5 PIR : attendre ~60 s de stabilisation apres mise sous tension");
  Serial.println("T6 Porte : ouvrir / fermer ; T7 : presenter un badge");
}

void loop() {
  static int lastPir = -1, lastDoor = -1;
  int pir = digitalRead(PIR_PIN), door = digitalRead(DOOR_PIN) ^ DOOR_IS_BUTTON;
  if (pir != lastPir)  { Serial.printf("PIR  = %d (%s)\n", pir, pir ? "MOUVEMENT" : "calme"); lastPir = pir; }
  if (door != lastDoor){ Serial.printf("DOOR = %d (%s)\n", door, door ? "OUVERTE" : "fermee"); lastDoor = door; }
  digitalWrite(LED_PIN, pir);
  // RC522 relu toutes les 2 s : permet de corriger le câblage carte sous tension
  static unsigned long lastV = 0;
  static byte lastVer = 0xAA;
  if (millis() - lastV > 2000) {
    lastV = millis();
    rfid.PCD_Init();
    byte v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
    if (v != lastVer) { Serial.printf("RC522 VersionReg = 0x%02X\n", v); lastVer = v; }
  }
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    Serial.print("Badge UID : ");
    for (byte i = 0; i < rfid.uid.size; i++) Serial.printf("%02X ", rfid.uid.uidByte[i]);
    Serial.println();
    rfid.PICC_HaltA();
  }
  delay(50);
}
