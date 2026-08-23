#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  Serial.println("ESP32 simulator booting...");
}

void loop() {
  // Placeholder loop for early simulation and integration tests.
  delay(1000);
  Serial.println("Heartbeat");
}

