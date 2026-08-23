#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

const char* ssid = "Wokwi-GUEST";
const char* password = "";
const char* mqtt_server = "broker.hivemq.com";
const char* topic_telemetry = "ufg/vision/telemetry";

WiFiClient espClient;
PubSubClient client(espClient);

const int PIN_ENA = 25; // Motor Esquerdo (LED Vermelho no Wokwi)
const int PIN_ENB = 14; // Motor Direito (LED Azul no Wokwi)

unsigned long lastPacketTime = 0;
const unsigned long WATCHDOG_TIMEOUT = 500;
bool isTracking = false;

// Controle PID
float Kp = 100.0;
float Ki = 0.0;
float Kd = 0.0;
float erroAnterior = 0.0;
float integral = 0.0;
int base_pwm = 150;

void stopMotors() {
    ledcWrite(0, 0);
    ledcWrite(1, 0);
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
    lastPacketTime = millis();

    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, payload, length);

    if (error) {
        Serial.println("Erro: Falha na desserialização do JSON");
        return;
    }

    isTracking = doc["tracking"];
    if (!isTracking) {
        stopMotors();
        Serial.println("Alvo perdido. Motores parados.");
        return;
    }

    float x_norm = doc["x"];

    float erro = x_norm;
    integral += erro;
    float derivada = erro - erroAnterior;

    float pid_output = (Kp * erro) + (Ki * integral) + (Kd * derivada);
    erroAnterior = erro;

    int pwm_esquerdo = base_pwm + pid_output;
    int pwm_direito  = base_pwm - pid_output;

    pwm_esquerdo = constrain(pwm_esquerdo, 0, 255);
    pwm_direito = constrain(pwm_direito, 0, 255);

    ledcWrite(0, pwm_esquerdo);
    ledcWrite(1, pwm_direito);

    Serial.printf("X: %.2f | PID: %.2f | PWM_E: %d | PWM_D: %d\n", x_norm, pid_output, pwm_esquerdo, pwm_direito);
}

void reconnect() {
    while (!client.connected()) {
        Serial.print("Conectando ao Broker MQTT...");
        String clientId = "ESP32_Vision_";
        clientId += String(random(0xffff), HEX);
        if (client.connect(clientId.c_str())) {
            Serial.println(" Conectado!");
            client.subscribe(topic_telemetry);
        } else {
            Serial.print(" Falha, rc=");
            Serial.print(client.state());
            Serial.println(" Tentando novamente em 5s");
            delay(5000);
        }
    }
}

void setup() {
    Serial.begin(115200);

    ledcSetup(0, 5000, 8);
    ledcSetup(1, 5000, 8);
    ledcAttachPin(PIN_ENA, 0);
    ledcAttachPin(PIN_ENB, 1);

    stopMotors();

    WiFi.begin(ssid, password);
    Serial.print("Conectando ao Wi-Fi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWi-Fi Conectado.");

    client.setServer(mqtt_server, 1883);
    client.setCallback(mqttCallback);
}

void loop() {
    if (!client.connected()) {
        stopMotors();
        reconnect();
    }
    client.loop();

    if (isTracking && (millis() - lastPacketTime > WATCHDOG_TIMEOUT)) {
        Serial.println("ALERTA: Watchdog desarmou os motores (Timeout de Rede)");
        stopMotors();
        isTracking = false;
    }
}