// esp32-sec-01 : sécurité & accès (PIR, contact de porte, RFID RC522, servo-serrure, buzzer, LED rouge et verte)
//
// Toute la logique de sécurité est LOCALE : la serrure, le contrôle des badges et l'alarme
// fonctionnent même si le hub ou le Wi-Fi sont coupés. Le hub supervise et commande.
#include <Arduino.h>
#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>
#include <Preferences.h>
#include "mysa_net.h"

const int PIR_PIN    = 13;   // HC-SR501 OUT
const int DOOR_PIN   = 14;   // contact MC-38 (ou bouton) vers GND, pull-up interne
const int BUZZER_PIN = 25;   // module buzzer actif (IN)
const int LED_PIN    = 26;   // LED rouge + 220 ohms : alertes seulement (alarme, badge refusé, lecteur bloqué)
const int LED_OK_PIN = 21;   // LED verte + 220 ohms : allumée tant que la serrure est ouverte
const int SERVO_PIN  = 27;   // servo SG90 (alimentation 5 V séparée, masse commune)
const int SS_PIN     = 5;    // RC522 SDA ; SCK=18, MISO=19, MOSI=23
const int RST_PIN    = 22;   // RC522 RST

const bool DOOR_ENABLED   = false;  // passer à true une fois le MC-38 câblé
const bool DOOR_IS_BUTTON = false;  // true : bouton (appui = ouverte) ; false : contact MC-38
const int LOCK_CLOSED = 0, LOCK_OPEN = 90;      // angles du servo (degrés)

const unsigned long PIR_PERIOD_MS = 2000;
const unsigned long UNLOCK_MS     = 5000;       // durée d'ouverture de la serrure
const unsigned long ENTRY_MS      = 60000;      // fenêtre d'entrée après un badge valide
const unsigned long ALARM_MS      = 60000;      // durée max de la sirène
const unsigned long EXIT_MS       = 30000;      // délai de sortie après armement
const int  MAX_REFUSED            = 5;          // badges refusés tolérés...
const unsigned long REFUSED_WINDOW_MS = 60000;  // ...sur cette fenêtre
const unsigned long LOCKOUT_MS    = 30000;      // lecteur bloqué ensuite
const unsigned long REFUSED_LED_MS = 2000;      // LED rouge allumée après un badge refusé
const char* DEFAULT_BADGES = "29 2F 3A 03";     // liste initiale (séparateur ';')

MFRC522 rfid(SS_PIN, RST_PIN);
Servo lock;
Preferences prefs;

String badges;                                   // UID autorisés, "AA BB CC DD;..."
bool armed = false, lockOpen = false, alarmOn = false;
int ledForced = -1;                              // -1 : la LED signale les alertes ; 1 : forcée par "led on"
int motionSeen = 0, doorOpen = 0;
unsigned long unlockedAt = 0, lastValidBadge = 0, alarmAt = 0, lockoutUntil = 0, armedAt = 0;
unsigned long refusedLedUntil = 0;
unsigned long refusedAt[MAX_REFUSED] = {0};
int refusedIdx = 0;

// ---------------------------------------------------------------- badges (NVS)
int badgeCount() {
  if (badges.isEmpty()) return 0;
  int n = 1;
  for (char ch : badges) if (ch == ';') n++;
  return n;
}
bool isAuthorized(const String& uid) {
  return (";" + badges + ";").indexOf(";" + uid + ";") >= 0;
}
void saveBadges() {
  prefs.putString("badges", badges);
  publishSensor("badges", badgeCount(), "count");
}
void addBadge(String uid) {
  uid.trim(); uid.toUpperCase();
  if (uid.length() < 8 || isAuthorized(uid)) return;
  badges = badges.isEmpty() ? uid : badges + ";" + uid;
  saveBadges();
}
void delBadge(String uid) {
  uid.trim(); uid.toUpperCase();
  String l = ";" + badges + ";";
  l.replace(";" + uid + ";", ";");
  badges = l.length() > 1 ? l.substring(1, l.length() - 1) : "";
  saveBadges();
}

// ---------------------------------------------------------------- état publié
void setLock(bool open) {
  if (open == lockOpen) return;
  lockOpen = open;
  lock.write(open ? LOCK_OPEN : LOCK_CLOSED);
  digitalWrite(LED_OK_PIN, open);
  if (open) unlockedAt = millis();
  publishSensor("lock", lockOpen, "bool");
}
// Alarme effective après le délai de sortie (le temps de quitter la pièce après l'armement)
bool armedActive() { return armed && millis() - armedAt > EXIT_MS; }
void setArmed(bool on) {
  armed = on;
  armedAt = millis();
  prefs.putBool("armed", on);
  publishSensor("arm", armed, "bool");
}
void setAlarm(bool on, const char* why = "") {
  if (on == alarmOn) return;
  alarmOn = on;
  if (on) alarmAt = millis();
  digitalWrite(BUZZER_PIN, on);
  Serial.printf("[ALARME] %s %s\n", on ? "DECLENCHEE" : "arretee", why);
  if (on) publishEvent("alarm", 1, "bool", "cause", why);
  else publishSensor("alarm", 0, "bool");
}
// Bips courts (bloquant, < 1 s ; le réseau tourne dans sa propre tâche). Le buzzer reprend
// ensuite l'état de l'alarme, pour ne pas couper une sirène en cours.
void beep(int n) {
  for (int i = 0; i < n; i++) {
    digitalWrite(BUZZER_PIN, HIGH); delay(100);
    digitalWrite(BUZZER_PIN, LOW);  delay(100);
  }
  digitalWrite(BUZZER_PIN, alarmOn);
}
void publishStates() {           // état complet, à chaque (re)connexion
  publishSensor("arm", armed, "bool");
  publishSensor("lock", lockOpen, "bool");
  publishSensor("alarm", alarmOn, "bool");
  if (DOOR_ENABLED) publishSensor("door", doorOpen, "bool");
  publishSensor("badges", badgeCount(), "count");
}

// 1 = porte ouverte. MC-38 : aimant présent = contact fermé = LOW. Bouton : appui = LOW = ouverte.
int readDoor() { return digitalRead(DOOR_PIN) ^ DOOR_IS_BUTTON; }

String uidToString(const MFRC522::Uid& uid) {
  char buf[32] = "";
  for (byte i = 0; i < uid.size && i < 10; i++)
    snprintf(buf + strlen(buf), sizeof(buf) - strlen(buf), i ? " %02X" : "%02X", uid.uidByte[i]);
  return String(buf);
}

// ---------------------------------------------------------------- commandes
void handleCommand(const MysaCmd& c) {
  bool on = !strcmp(c.value, "on") || !strcmp(c.value, "1") || !strcmp(c.value, "open");
  if (!strcmp(c.act, "lock")) { setLock(on); if (on) lastValidBadge = millis(); }
  else if (!strcmp(c.act, "arm")) { setArmed(on); if (!on) setAlarm(false, "desarmement"); }
  else if (!strcmp(c.act, "alarm")) setAlarm(on, "commande");
  else if (!strcmp(c.act, "buzzer")) digitalWrite(BUZZER_PIN, on);
  else if (!strcmp(c.act, "led")) ledForced = on ? 1 : -1;     // off : la LED revient aux alertes
  else if (!strcmp(c.act, "badge_add")) addBadge(c.value);
  else if (!strcmp(c.act, "badge_del")) delBadge(c.value);
}

// ---------------------------------------------------------------- RFID
void readBadge() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;
  String uid = uidToString(rfid.uid);
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  if (millis() < lockoutUntil) {
    Serial.printf("[RFID] %s ignore (lecteur bloque encore %lu s)\n", uid.c_str(), (lockoutUntil - millis()) / 1000 + 1);
    return;
  }
  bool ok = isAuthorized(uid);
  Serial.printf("[RFID] badge %s -> %s\n", uid.c_str(), ok ? "AUTORISE" : "REFUSE");
  publishEvent("rfid", ok ? 1 : 0, "bool", "uid", uid.c_str());
  if (ok) {
    lastValidBadge = millis();
    setAlarm(false, "badge valide");
    if (armed) setArmed(false);                // badge valide = désarmement
    setLock(true);                             // LED verte allumée tant que la serrure est ouverte
    beep(1);
    return;
  }
  // Badge refusé : LED rouge quelques secondes + 2 bips
  refusedLedUntil = millis() + REFUSED_LED_MS;
  digitalWrite(LED_PIN, HIGH);
  beep(2);
  // Anti force brute : MAX_REFUSED refus en REFUSED_WINDOW_MS -> lecteur bloqué
  refusedAt[refusedIdx] = millis();
  refusedIdx = (refusedIdx + 1) % MAX_REFUSED;
  unsigned long oldest = refusedAt[refusedIdx];
  if (oldest && millis() - oldest < REFUSED_WINDOW_MS) {
    lockoutUntil = millis() + LOCKOUT_MS;
    memset(refusedAt, 0, sizeof(refusedAt));
    Serial.printf("[RFID] %d refus : lecteur bloque %lu s\n", MAX_REFUSED, LOCKOUT_MS / 1000);
    publishSensor("rfid_lockout", LOCKOUT_MS / 1000, "s");   // durée du blocage : compte à rebours au dashboard
    beep(3);
  }
}

// ---------------------------------------------------------------- setup / loop
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n=== Mysa esp32-sec-01 (securite & acces) ===");
  pinMode(PIR_PIN, INPUT);
  pinMode(DOOR_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  pinMode(LED_OK_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_PIN, LOW);
  digitalWrite(LED_OK_PIN, LOW);

  prefs.begin("mysa", false);
  badges = prefs.getString("badges", DEFAULT_BADGES);
  armed = prefs.getBool("armed", false);
  Serial.printf("[NVS] %d badge(s), alarme %s\n", badgeCount(), armed ? "armee" : "desarmee");

  lock.setPeriodHertz(50);
  lock.attach(SERVO_PIN, 500, 2400);
  lock.write(LOCK_CLOSED);                       // état sûr au démarrage : serrure fermée

  SPI.begin();
  rfid.PCD_Init();
  byte v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.printf("[RFID] version 0x%02X %s\n", v, (v == 0x00 || v == 0xFF) ? "<- ECHEC cablage SPI" : "OK");
  if (DOOR_ENABLED) doorOpen = readDoor();
  setupNet();
}

void loop() {
  static bool wasUp = false;
  bool up = netConnected();
  if (up && !wasUp) publishStates();
  wasUp = up;

  MysaCmd c;
  while (pollCommand(c)) handleCommand(c);

  readBadge();
  unsigned long now = millis();
  bool entryWindow = lastValidBadge && now - lastValidBadge < ENTRY_MS;

  // Porte : publication sur changement (flux événementiel)
  if (DOOR_ENABLED) {
    int d = readDoor();
    if (d != doorOpen) {
      doorOpen = d;
      publishSensor("door", doorOpen, "bool");
      if (doorOpen && armedActive() && !entryWindow) setAlarm(true, "porte ouverte sans badge");
    }
  }

  // PIR : mouvement verrouillé entre deux publications (flux périodique)
  int motion = digitalRead(PIR_PIN);
  motionSeen |= motion;
  if (motion && armedActive() && !entryWindow) setAlarm(true, "mouvement alarme armee");

  // Serrure : refermeture automatique (attend la fermeture de la porte si le contact existe)
  if (lockOpen && now - unlockedAt > UNLOCK_MS && !(DOOR_ENABLED && doorOpen)) setLock(false);

  if (alarmOn && now - alarmAt > ALARM_MS) setAlarm(false, "fin de temporisation");
  if (millis() >= lockoutUntil && lockoutUntil) { lockoutUntil = 0; publishSensor("rfid_lockout", 0, "s"); }

  // LED rouge = alertes seulement : clignote vite en alarme, fixe après un badge refusé, lente
  // pendant le blocage du lecteur, éteinte sinon (un simple mouvement ne l'allume plus).
  if (alarmOn) digitalWrite(LED_PIN, (now / 250) % 2);
  else if (now < refusedLedUntil) digitalWrite(LED_PIN, HIGH);
  else if (lockoutUntil) digitalWrite(LED_PIN, (now / 1000) % 2);
  else digitalWrite(LED_PIN, ledForced == 1);

  static unsigned long last = 0;
  if (now - last >= PIR_PERIOD_MS) {
    last = now;
    publishSensor("pir", motionSeen, "bool");
    motionSeen = motion;
  }
  delay(10);
}
