#include <WiFi.h>
#include <Adafruit_MQTT.h>
#include <Adafruit_MQTT_Client.h>
#include <ESP32Servo.h>
#include <Preferences.h>

Preferences preferences;

// WiFi Configuration
const char* WIFI_SSID = "CJNet";
const char* WIFI_PASS = "chami1234";

// Adafruit IO Configuration
#define AIO_SERVER "io.adafruit.com"
#define AIO_PORT 1883
#define AIO_USERNAME "chamijaye"
#define AIO_KEY "aio_rXpS382omXMlqvUl2WcDUlZcmWUT"

// Pin Configuration
const int ULTRASONIC_PINS[2][2] = {{13, 12}, {14, 27}}; // Trig, Echo
const int LED_PINS[2][3] = {{33, 32, 25}, {26, 17, 16}}; // R, G, B
#define SERVO_PIN 5    // Gate control
#define PIR_PIN 23     // Vehicle detection

// MQTT Clients
WiFiClient client;
Adafruit_MQTT_Client mqtt(&client, AIO_SERVER, AIO_PORT, AIO_USERNAME, AIO_KEY);

// Feeds
Adafruit_MQTT_Publish slot_feeds[2] = {
  Adafruit_MQTT_Publish(&mqtt, AIO_USERNAME "/feeds/parking.slot1"),
  Adafruit_MQTT_Publish(&mqtt, AIO_USERNAME "/feeds/parking.slot2")
};
Adafruit_MQTT_Subscribe gate_sub = Adafruit_MQTT_Subscribe(&mqtt, AIO_USERNAME "/feeds/parking.gate");
Adafruit_MQTT_Subscribe reservation_sub = Adafruit_MQTT_Subscribe(&mqtt, AIO_USERNAME "/feeds/reservations");

Servo gateServo;

struct SlotState {
  bool occupied;
  bool reserved;
  String reservedBy;
};
SlotState slots[2];

void setup() {
  Serial.begin(115200);
  delay(1000);

  // Initialize preferences (flash storage)
  preferences.begin("parking", false);
  preferences.clear(); // Uncomment this once to clear flash storage
  loadReservations();

  // Initialize hardware
  initializeHardware();

  // Connect WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while(WiFi.status() != WL_CONNECTED) delay(500);
  Serial.println("WiFi Connected");
  // Setup MQTT
  mqtt.subscribe(&gate_sub);
  mqtt.subscribe(&reservation_sub);
}


void loadReservations() {
  for(int i=0; i<2; i++) {
    String key = "slot" + String(i+1); // Change from "slot0" to "slot1"/"slot2"
    slots[i].reserved = preferences.getBool((key + "_reserved").c_str(), false);
    slots[i].reservedBy = preferences.getString((key + "_name").c_str(), "");
  }
}

void saveReservation(int slot, bool reserved, String name) {
  String key = "slot" + String(slot+1); // Correct key format
  preferences.putBool((key + "_reserved").c_str(), reserved);
  preferences.putString((key + "_name").c_str(), name);
}

void initializeHardware() {
  for(int i=0; i<2; i++) {
    pinMode(ULTRASONIC_PINS[i][0], OUTPUT);
    pinMode(ULTRASONIC_PINS[i][1], INPUT);
    for(int j=0; j<3; j++) {
      pinMode(LED_PINS[i][j], OUTPUT);
      digitalWrite(LED_PINS[i][j], LOW);
    }
    updateLEDs(i);
  }

  // Servo setup
  ESP32PWM::allocateTimer(0);
  gateServo.setPeriodHertz(50);
  gateServo.attach(SERVO_PIN, 500, 2400);
  closeGate();

  // PIR sensor
  pinMode(PIR_PIN, INPUT);
}

void loop() {
  if(!mqtt.connected()) connectMQTT();
  mqtt.processPackets(1000);
  handleMQTT();

  static unsigned long lastUpdate = 0;
  if(millis() - lastUpdate >= 500) {
    for(int i=0; i<2; i++) {
      updateSlot(i);
    }
    lastUpdate = millis();
  }

  if(digitalRead(PIR_PIN)) triggerGate();
}

void handleMQTT() {
  Adafruit_MQTT_Subscribe *subscription;
  while((subscription = mqtt.readSubscription(5000))) {
    if(subscription == &gate_sub) {
      String message = (char*)gate_sub.lastread;
      if(message == "Open") openGate();
      else if(message == "Closed") closeGate();
    }
    else if(subscription == &reservation_sub) {
      String message = (char*)reservation_sub.lastread;
      processReservation(message);
    }
  }
}

void processReservation(String message) {
  // Format: "slot|action|name|email" (action: 1=reserve, 0=cancel)
  String parts[4];
  int prevPos = 0;
  for(int i=0; i<4; i++) {
    int pos = message.indexOf('|', prevPos);
    if(pos == -1) pos = message.length();
    parts[i] = message.substring(prevPos, pos);
    prevPos = pos + 1;
  }

  int slot = parts[0].toInt() - 1;
  if(slot < 0 || slot > 1) return;

  if(parts[1] == "1") { // Reserve
    slots[slot].reserved = true;
    slots[slot].reservedBy = parts[2];
    saveReservation(slot, true, parts[2]);
  } 
  else { // Cancel
    slots[slot].reserved = false;
    slots[slot].reservedBy = "";
    saveReservation(slot, false, "");
  }
  
  updateLEDs(slot);
  updateSlotStatus(slot);
}

void updateSlot(int slot) {
  float distance = getDistance(slot);
  slots[slot].occupied = (distance < 10);
  updateLEDs(slot);
  updateSlotStatus(slot);
}

void updateSlotStatus(int slot) {
  String status;
  if(slots[slot].reserved) status = "Reserved";
  else if(slots[slot].occupied) status = "Occupied";
  else status = "Free";
  
  Serial.printf("Slot %d: %s (Reserved: %s, Distance: %.2f cm)\n", 
              slot+1, status.c_str(), 
              slots[slot].reserved ? "Yes" : "No", 
              getDistance(slot));
  slot_feeds[slot].publish(status.c_str());
}

void updateLEDs(int slot) {
  digitalWrite(LED_PINS[slot][0], slots[slot].occupied && !slots[slot].reserved);
  digitalWrite(LED_PINS[slot][1], !slots[slot].occupied && !slots[slot].reserved);
  digitalWrite(LED_PINS[slot][2], slots[slot].reserved);
}


float getDistance(int slot) {
  digitalWrite(ULTRASONIC_PINS[slot][0], LOW);
  delayMicroseconds(2);
  digitalWrite(ULTRASONIC_PINS[slot][0], HIGH);
  delayMicroseconds(10);
  digitalWrite(ULTRASONIC_PINS[slot][0], LOW);
  
  long duration = pulseIn(ULTRASONIC_PINS[slot][1], HIGH, 30000);
  return duration * 0.034 / 2;
}

void triggerGate() {
  if(gateServo.read() <= 10) {
    openGate();
    delay(5000);
    closeGate();
  }
}

// Modify servo control functions
void openGate() {
  for(int pos = 0; pos <= 60; pos += 1) {
    gateServo.write(pos);
    delay(15);
  }
  Serial.println("Gate opened");
}

void closeGate() {
  for(int pos = 60; pos >= 0; pos -= 1) {
    gateServo.write(pos);
    delay(15);
  }
  Serial.println("Gate closed");
}

void connectMQTT() {
  while(mqtt.connect() != 0) {
    delay(2000);
  }
}
