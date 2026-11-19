// AIoT Machine Health — เฟิร์มแวร์บอร์ด Cucumber RS (ESP32-S2)
//
// หน้าที่ของบอร์ด
//   1. อ่านความเร่งจาก MPU-6050 ที่ 200 Hz แล้วสรุปทุก 1 วินาทีเป็นค่า RMS และ peak ของ "ส่วนที่สั่น"
//   2. อ่านอุณหภูมิ/ความชื้นจาก HTS221
//   3. ส่ง JSON ทาง MQTT ไปที่ gateway แล้วรอคำสั่งสีไฟกลับมา
//   4. ถ้า gateway เงียบเกิน 10 วินาที ใช้กฎสำรองในบอร์ดเอง (ไฟม่วง / แดงกะพริบ)
//
// บอร์ดไม่ได้ตัดสินสถานะเอง ยกเว้นตอนติดต่อ gateway ไม่ได้

#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_HTS221.h>
#include <Adafruit_NeoPixel.h>
#include "secrets.h"   // คัดลอกจาก include/secrets.h.example

// ---------------- ขาของบอร์ด Cucumber RS ----------------
constexpr int PIN_SDA = 41;
constexpr int PIN_SCL = 40;
constexpr int PIN_RGB = 18;            // WS2812B 1 ดวง

// ---------------- การสุ่มตัวอย่าง ----------------
constexpr uint32_t SAMPLE_US = 5000;   // 200 Hz
constexpr uint16_t WINDOW_N = 200;     // 200 ค่า = 1 วินาที
constexpr uint32_t STATE_TIMEOUT_MS = 10000;
constexpr float OFFLINE_ALARM_RMS = 2.5f;   // m/s² กฎสำรองตอนไม่มี gateway

Adafruit_MPU6050 mpu;
Adafruit_HTS221 hts;
bool htsOk = false;
Adafruit_NeoPixel rgb(1, PIN_RGB, NEO_GRB + NEO_KHZ800);
WiFiClient net;
PubSubClient mqtt(net);

String tTelemetry, tStatus, tState;

// ผลรวมในหน้าต่าง 1 วินาที (ใช้ double เพราะต้องลบเลขใกล้กัน ~9.8² ออกจากกัน)
struct Window {
  double sx, sy, sz, sxx, syy, szz;
  float peak;
  uint16_t n;
} win = {};
float meanX = 0, meanY = 0, meanZ = 0;   // ค่าเฉลี่ยของหน้าต่างก่อน (= แรงโน้มถ่วง + ท่าทางการติดตั้ง)
bool haveMean = false;

uint32_t seq = 0, lastSampleUs = 0, lastStateMs = 0, lastMqttTryMs = 0;
float lastRms = 0;
char currentLed[8] = "";

// ---------------- ไฟ RGB ----------------
void showColor(uint8_t r, uint8_t g, uint8_t b) {
  rgb.setPixelColor(0, rgb.Color(r, g, b));
  rgb.show();
}

bool applyLed(const char* name) {
  if (!strcmp(name, "green"))       showColor(0, 40, 0);
  else if (!strcmp(name, "yellow")) showColor(45, 30, 0);
  else if (!strcmp(name, "red"))    showColor(70, 0, 0);
  else if (!strcmp(name, "white"))  showColor(25, 25, 25);
  else if (!strcmp(name, "blue"))   showColor(0, 0, 60);
  else return false;                 // ไม่อยู่ใน allowlist = ไม่ทำตาม
  return true;
}

// ---------------- MQTT ----------------
void onMessage(char* topic, byte* payload, unsigned int len) {
  if (tState != topic) return;
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) {
    Serial.println("<- state: JSON ผิดรูปแบบ ไม่ทำตาม");
    return;
  }
  // ตรวจทุก field ก่อนเปลี่ยนไฟ (ไม่เชื่อข้อความที่ส่งมาโดยไม่ตรวจ)
  if ((doc["v"] | 0) != 1 || strcmp(doc["device_id"] | "", DEVICE_ID) != 0) return;
  const char* led = doc["led"] | "";
  if (!applyLed(led)) {
    Serial.printf("<- state: led '%s' ไม่อยู่ใน allowlist\n", led);
    return;
  }
  strlcpy(currentLed, led, sizeof(currentLed));
  lastStateMs = millis();
  Serial.printf("<- %s (%s) %s\n", doc["state"] | "?", led, doc["reason"] | "");
}

void ensureMqtt() {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  if (millis() - lastMqttTryMs < 5000) return;     // ลองใหม่ทุก 5 วินาที โดยไม่หยุดการวัด
  lastMqttTryMs = millis();
  String clientId = String("cucumber-") + DEVICE_ID;
  Serial.printf("MQTT -> %s:%d ... ", MQTT_HOST, MQTT_PORT);
  // Last Will: ถ้าบอร์ดหลุด broker จะประกาศ "offline" แทนบอร์ด
  if (mqtt.connect(clientId.c_str(), nullptr, nullptr, tStatus.c_str(), 1, true, "offline")) {
    Serial.println("connected");
    mqtt.publish(tStatus.c_str(), "online", true);
    mqtt.subscribe(tState.c_str());
  } else {
    Serial.printf("failed rc=%d\n", mqtt.state());
  }
}

// ---------------- การวัดการสั่น ----------------
void addSample(float x, float y, float z) {
  win.sx += x;  win.sy += y;  win.sz += z;
  win.sxx += (double)x * x;  win.syy += (double)y * y;  win.szz += (double)z * z;
  if (haveMean) {
    float dx = x - meanX, dy = y - meanY, dz = z - meanZ;
    float m = sqrtf(dx * dx + dy * dy + dz * dz);
    if (m > win.peak) win.peak = m;
  }
  win.n++;
}

void offlineRule() {
  // gateway เงียบ: ม่วง = ออฟไลน์แต่ปกติ, แดงกะพริบ = ออฟไลน์และสั่นเกินกฎสำรอง
  if (lastRms >= OFFLINE_ALARM_RMS) {
    if ((millis() / 500) % 2) showColor(70, 0, 0); else showColor(0, 0, 0);
  } else {
    showColor(20, 0, 25);
  }
}

void finishWindow() {
  const double n = win.n;
  const double mx = win.sx / n, my = win.sy / n, mz = win.sz / n;
  // ความแปรปรวนรวม 3 แกน = พลังงานของส่วนที่สั่น (ตัดแรงโน้มถ่วงที่เป็นค่าคงที่ออกแล้ว)
  const double var = max(0.0, win.sxx / n - mx * mx) + max(0.0, win.syy / n - my * my) +
                     max(0.0, win.szz / n - mz * mz);
  const float rms = sqrt(var);
  const float peak = win.peak;
  const bool firstWindow = !haveMean;
  meanX = mx;  meanY = my;  meanZ = mz;  haveMean = true;
  lastRms = rms;
  win = {};
  if (firstWindow) return;   // หน้าต่างแรกยังไม่มีค่าเฉลี่ยสำหรับคำนวณ peak

  JsonDocument doc;
  doc["v"] = 1;
  doc["device_id"] = DEVICE_ID;
  doc["seq"] = seq++;
  doc["vib_rms"] = roundf(rms * 10000) / 10000;
  doc["vib_peak"] = roundf(peak * 10000) / 10000;
  if (htsOk) {
    sensors_event_t hum, temp;
    hts.getEvent(&hum, &temp);
    doc["temp"] = roundf(temp.temperature * 100) / 100;
    doc["hum"] = roundf(hum.relative_humidity * 10) / 10;
  }
  doc["rssi"] = WiFi.RSSI();
  doc["uptime_s"] = millis() / 1000;

  char buf[256];
  size_t len = serializeJson(doc, buf);
  bool ok = mqtt.connected() && mqtt.publish(tTelemetry.c_str(), (const uint8_t*)buf, len);
  Serial.printf("-> seq=%lu rms=%.3f peak=%.3f %s\n", (unsigned long)(seq - 1), rms, peak,
                ok ? "sent" : "NOT sent");
}

// ---------------- setup / loop ----------------
void setup() {
  Serial.begin(115200);
  delay(300);
  rgb.begin();
  showColor(20, 0, 25);   // ม่วง = กำลังเริ่ม/ออฟไลน์

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);
  if (!mpu.begin(0x68, &Wire)) {
    Serial.println("ไม่พบ MPU-6050 (0x68) — ตรวจขา I2C");
    while (true) { showColor(70, 0, 0); delay(200); showColor(0, 0, 0); delay(200); }
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  mpu.setFilterBandwidth(MPU6050_BAND_94_HZ);   // กรองความถี่สูงกว่า Nyquist (100 Hz) ออก
  htsOk = hts.begin_I2C();                       // 0x5F
  Serial.printf("MPU-6050 OK, HTS221 %s\n", htsOk ? "OK" : "ไม่พบ (ส่งเฉพาะการสั่น)");

  String base = String("aiot/machines/") + DEVICE_ID;
  tTelemetry = base + "/telemetry";
  tStatus = base + "/status";
  tState = base + "/state";

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("WiFi -> %s\n", WIFI_SSID);

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setBufferSize(512);
  mqtt.setSocketTimeout(2);
  lastSampleUs = micros();
}

void loop() {
  static bool wifiShown = false;
  if (WiFi.status() == WL_CONNECTED && !wifiShown) {
    Serial.printf("WiFi connected, IP %s, RSSI %d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
    wifiShown = true;
  }
  ensureMqtt();
  mqtt.loop();

  const uint32_t now = micros();
  if (now - lastSampleUs >= SAMPLE_US) {
    lastSampleUs += SAMPLE_US;
    if (now - lastSampleUs > 10 * SAMPLE_US) lastSampleUs = now;   // ช้าไปมาก (เช่นตอนต่อ MQTT) ไม่ต้องไล่ตาม
    sensors_event_t a, g, t;
    mpu.getEvent(&a, &g, &t);
    addSample(a.acceleration.x, a.acceleration.y, a.acceleration.z);
    if (win.n >= WINDOW_N) {
      finishWindow();
      if (millis() - lastStateMs > STATE_TIMEOUT_MS) offlineRule();
    }
  }
}
