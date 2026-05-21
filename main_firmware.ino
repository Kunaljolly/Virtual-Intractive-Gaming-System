/*
 * Ra.One Motion Gaming Controller Firmware
 * Inspired by PlayStation Move + Ra.One movie
 * Hardware: ESP32 + MPU6050 + Flex Sensors
 *
 * Movement → Action Mapping:
 *   Sharp forward arm thrust  → PUNCH
 *   Fast downward leg swing   → KICK
 *   Cross-arm guard pose      → BLOCK
 *   Upward jump motion        → JUMP
 *   360° spin + thrust        → SPECIAL MOVE (G.One Energy Blast)
 */

#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <MPU6050.h>
#include <ArduinoJson.h>

// ─── PIN CONFIG ──────────────────────────────────────────────────────────────
#define FLEX_PUNCH_PIN  34   // Flex sensor on forearm (ADC)
#define FLEX_BLOCK_PIN  35   // Flex sensor on upper arm (ADC)
#define FLEX_KICK_PIN   32   // Flex sensor on leg (ADC)
#define LED_PIN         2    // Built-in LED for action feedback

// ─── WIFI / UDP CONFIG ───────────────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASS";
const char* PC_IP         = "192.168.1.100";  // PC running Tekken 3
const int   UDP_PORT      = 4210;

WiFiUDP udp;
MPU6050 mpu;

// ─── MOVEMENT THRESHOLDS (tune during calibration) ───────────────────────────
struct Thresholds {
  float punchAccelX    = 2.5f;   // g-force for punch detection
  float kickAccelZ     = 2.0f;   // g-force for kick detection
  float jumpAccelY     = 2.8f;   // g-force for jump detection
  float blockGyroZ     = 150.0f; // deg/s for block rotation
  float specialGyroAll = 200.0f; // combined gyro for special move
  int   flexPunchMin   = 2800;   // ADC value for bent punch arm
  int   flexBlockMin   = 2600;   // ADC value for block pose
  int   flexKickMin    = 2700;   // ADC value for kick leg
  unsigned long cooldownMs = 400; // ms between same action triggers
};

Thresholds thresh;

// ─── STATE ───────────────────────────────────────────────────────────────────
int16_t ax, ay, az, gx, gy, gz;
float   axG, ayG, azG, gxDps, gyDps, gzDps;

enum Action { NONE, PUNCH, KICK, BLOCK, JUMP, SPECIAL };
Action lastAction = NONE;
unsigned long lastActionTime = 0;

// Calibration offsets (set during calibration phase)
int16_t axOffset = 0, ayOffset = 0, azOffset = 0;
int16_t gxOffset = 0, gyOffset = 0, gzOffset = 0;

// ─── SETUP ───────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);

  Wire.begin(21, 22);  // SDA=21, SCL=22 on ESP32
  mpu.initialize();

  if (!mpu.testConnection()) {
    Serial.println("[ERROR] MPU6050 not found. Check wiring.");
    while (1) { blinkError(); }
  }
  Serial.println("[OK] MPU6050 connected.");

  calibrateSensors();
  connectWiFi();

  Serial.println("[READY] Ra.One Motion Controller online!");
}

// ─── MAIN LOOP ───────────────────────────────────────────────────────────────
void loop() {
  readSensors();
  Action detected = detectAction();

  if (detected != NONE) {
    unsigned long now = millis();
    if (detected != lastAction || (now - lastActionTime) > thresh.cooldownMs) {
      sendAction(detected);
      lastAction = detected;
      lastActionTime = now;
      flashLED();
      printActionDebug(detected);
    }
  }

  delay(10);  // ~100Hz polling rate
}

// ─── SENSOR READ ─────────────────────────────────────────────────────────────
void readSensors() {
  mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

  // Apply calibration offsets
  ax -= axOffset; ay -= ayOffset; az -= azOffset;
  gx -= gxOffset; gy -= gyOffset; gz -= gzOffset;

  // Convert to physical units
  axG   = ax / 16384.0f;   // ±2g range → g-force
  ayG   = ay / 16384.0f;
  azG   = az / 16384.0f;
  gxDps = gx / 131.0f;     // ±250 deg/s range
  gyDps = gy / 131.0f;
  gzDps = gz / 131.0f;
}

// ─── ACTION DETECTION ────────────────────────────────────────────────────────
Action detectAction() {
  int flexPunch = analogRead(FLEX_PUNCH_PIN);
  int flexBlock = analogRead(FLEX_BLOCK_PIN);
  int flexKick  = analogRead(FLEX_KICK_PIN);

  // SPECIAL MOVE: All gyros high + punch flex (spin + thrust)
  float totalGyro = abs(gxDps) + abs(gyDps) + abs(gzDps);
  if (totalGyro > thresh.specialGyroAll && flexPunch > thresh.flexPunchMin) {
    return SPECIAL;
  }

  // JUMP: Strong upward acceleration
  if (ayG > thresh.jumpAccelY) {
    return JUMP;
  }

  // PUNCH: Forward thrust + forearm bend
  if (axG > thresh.punchAccelX && flexPunch > thresh.flexPunchMin) {
    return PUNCH;
  }

  // KICK: Downward/lateral leg swing
  if (abs(azG) > thresh.kickAccelZ && flexKick > thresh.flexKickMin) {
    return KICK;
  }

  // BLOCK: Guard rotation + arm cross
  if (abs(gzDps) > thresh.blockGyroZ && flexBlock > thresh.flexBlockMin) {
    return BLOCK;
  }

  return NONE;
}

// ─── SEND ACTION OVER UDP ────────────────────────────────────────────────────
void sendAction(Action action) {
  StaticJsonDocument<128> doc;
  doc["action"]  = actionName(action);
  doc["axG"]     = axG;
  doc["ayG"]     = ayG;
  doc["azG"]     = azG;
  doc["gxDps"]   = gxDps;
  doc["gyDps"]   = gyDps;
  doc["gzDps"]   = gzDps;
  doc["ts"]      = millis();

  char buf[128];
  serializeJson(doc, buf);

  udp.beginPacket(PC_IP, UDP_PORT);
  udp.print(buf);
  udp.endPacket();
}

// ─── CALIBRATION ─────────────────────────────────────────────────────────────
void calibrateSensors() {
  Serial.println("[CAL] Calibrating... Hold still for 3 seconds.");
  delay(2000);

  const int samples = 200;
  long sumAx=0, sumAy=0, sumAz=0, sumGx=0, sumGy=0, sumGz=0;

  for (int i = 0; i < samples; i++) {
    mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
    sumAx += ax; sumAy += ay; sumAz += az;
    sumGx += gx; sumGy += gy; sumGz += gz;
    delay(5);
  }

  axOffset = sumAx / samples;
  ayOffset = sumAy / samples;
  azOffset = sumAz / samples - 16384; // Remove 1g gravity from Y
  gxOffset = sumGx / samples;
  gyOffset = sumGy / samples;
  gzOffset = sumGz / samples;

  Serial.printf("[CAL] Offsets — ax:%d ay:%d az:%d gx:%d gy:%d gz:%d\n",
                axOffset, ayOffset, azOffset, gxOffset, gyOffset, gzOffset);
  Serial.println("[CAL] Calibration complete!");
}

// ─── WIFI ────────────────────────────────────────────────────────────────────
void connectWiFi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[WIFI] Connecting");
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500); Serial.print("."); retries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WIFI] Connected: %s\n", WiFi.localIP().toString().c_str());
    udp.begin(UDP_PORT);
  } else {
    Serial.println("\n[WIFI] Failed — running in Serial-only mode.");
  }
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────
const char* actionName(Action a) {
  switch (a) {
    case PUNCH:   return "PUNCH";
    case KICK:    return "KICK";
    case BLOCK:   return "BLOCK";
    case JUMP:    return "JUMP";
    case SPECIAL: return "SPECIAL";
    default:      return "NONE";
  }
}

void printActionDebug(Action a) {
  Serial.printf("[ACTION] %-8s | aX:%.2f aY:%.2f aZ:%.2f | gX:%.1f gY:%.1f gZ:%.1f\n",
                actionName(a), axG, ayG, azG, gxDps, gyDps, gzDps);
}

void flashLED() {
  digitalWrite(LED_PIN, HIGH);
  delay(80);
  digitalWrite(LED_PIN, LOW);
}

void blinkError() {
  digitalWrite(LED_PIN, HIGH); delay(200);
  digitalWrite(LED_PIN, LOW);  delay(200);
}
