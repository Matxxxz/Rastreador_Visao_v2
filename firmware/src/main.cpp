#include <Arduino.h>
#include <WiFi.h>
#include "mqtt_config.h"

#if MQTT_USE_TLS
  #include <WiFiClientSecure.h>
#endif
#include <PubSubClient.h>
#include <ArduinoJson.h>

// Guard de compatibilidade: este firmware usa a API ledc do Arduino ESP32 Core 3.x.
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR < 3
  #error "Este firmware requer Arduino ESP32 Core >= 3.0.0. Atualize platform_packages no platformio.ini."
#endif

// Parâmetros de rede carregados de mqtt_config.h conforme ambiente (Wokwi, Local, Prod)
const char* ssid            = WIFI_SSID;
const char* password        = WIFI_PASS;
const char* mqtt_server     = MQTT_BROKER;
const int   mqtt_port       = MQTT_PORT;
const char* topic_telemetry = MQTT_TOPIC_TELEMETRY;

#if MQTT_USE_TLS
  WiFiClientSecure espClient;
#else
  WiFiClient       espClient;
#endif

PubSubClient client(espClient);

// --- Pinos de PWM ---
const int PIN_ENA = 25;  // Motor Esquerdo (LED Vermelho no Wokwi)
const int PIN_ENB = 14;  // Motor Direito  (LED Azul no Wokwi)
const int PWM_FREQ       = 5000;  // Hz
const int PWM_RESOLUTION = 8;     // bits → duty de 0 a 255

// --- Watchdog de Rede ---
unsigned long lastPacketTime    = 0;
const unsigned long WATCHDOG_TIMEOUT = 500;  // ms
bool isTracking = false;

// --- Controle PID (Tração Diferencial) ---
float Kp           = 120.0f;  // Ganho proporcional
float Ki           = 0.0f;
float Kd           = 0.0f;
float erroAnterior = 0.0f;
float integral     = 0.0f;
int   base_pwm     = 120;     // Velocidade base em marcha reta

// Anti-windup: teto do acumulador integral
const float MAX_INTEGRAL = 127.0f;

// Normalização do sensor pelo máximo prático da câmera
const float X_NORM_MAX_PRATICO = 0.74f;

// Zona-morta central: suprime micro-oscilações no centro
const float DEADZONE_CENTRO = 0.05f;

// --- Estado da máquina de reconexão MQTT não-bloqueante ---
enum class ReconnectState { IDLE, CONNECTING, WAITING };
ReconnectState reconnectState       = ReconnectState::IDLE;
unsigned long  reconnectLastAttempt = 0;
const unsigned long RECONNECT_INTERVAL = 5000;  // ms entre tentativas

// ---------------------------------------------------------------------------

void stopMotors() {
    ledcWrite(PIN_ENA, 0);
    ledcWrite(PIN_ENB, 0);
}

// ---------------------------------------------------------------------------
// Callback MQTT com validação estrita de segurança e integridade física.
// ---------------------------------------------------------------------------
void mqttCallback(char* topic, byte* payload, unsigned int length) {
    // 1. Validação de tópico: rejeitar mensagens de tópicos inesperados
    if (strcmp(topic, topic_telemetry) != 0) {
        Serial.printf("AVISO: Mensagem ignorada de topico nao autorizado: %s\n", topic);
        return;
    }

    // 2. Validação de tamanho: rejeitar payload vazio ou excessivo (> MAX_PAYLOAD_SIZE)
    if (length == 0 || length > MAX_PAYLOAD_SIZE) {
        Serial.printf("AVISO: Payload com tamanho invalido (%u bytes). Descartado.\n", length);
        stopMotors();
        integral     = 0.0f;
        erroAnterior = 0.0f;
        isTracking   = false;
        return;
    }

    // 3. Desserialização com tratamento de erro
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, payload, length);

    if (error) {
        Serial.printf("Erro: Falha na desserializacao do JSON (%s). Parada segura.\n", error.c_str());
        stopMotors();
        integral     = 0.0f;
        erroAnterior = 0.0f;
        isTracking   = false;
        return;
    }

    // 4. Validação de estrutura: deve ser um objeto JSON
    if (!doc.is<JsonObject>()) {
        Serial.println("Erro: Payload MQTT nao e um objeto JSON valido.");
        stopMotors();
        integral     = 0.0f;
        erroAnterior = 0.0f;
        isTracking   = false;
        return;
    }

    // 5. Validação de campos obrigatórios e tipos
    if (!doc["tracking"].is<bool>()) {
        Serial.println("Erro: Campo obrigatorio 'tracking' ausente ou tipo incorreto.");
        stopMotors();
        integral     = 0.0f;
        erroAnterior = 0.0f;
        isTracking   = false;
        return;
    }

    isTracking = doc["tracking"].as<bool>();
    if (!isTracking) {
        stopMotors();
        integral     = 0.0f;
        erroAnterior = 0.0f;
        lastPacketTime = millis();
        Serial.println("Alvo perdido. Motores parados. Integral resetada.");
        return;
    }

    if (!doc["x"].is<float>()) {
        Serial.println("Erro: Campo obrigatorio 'x' ausente ou tipo incorreto.");
        stopMotors();
        integral     = 0.0f;
        erroAnterior = 0.0f;
        isTracking   = false;
        return;
    }

    float x_val = doc["x"].as<float>();

    // 6. Proteção contra NaN e Infinito
    if (isnan(x_val) || isinf(x_val)) {
        Serial.println("Erro: Campo 'x' contem NaN ou Infinito. Parada segura.");
        stopMotors();
        integral     = 0.0f;
        erroAnterior = 0.0f;
        isTracking   = false;
        return;
    }

    // 7. Clamping rígido na entrada para intervalo de projeto [-1.0, 1.0]
    float x_norm = constrain(x_val, -1.0f, 1.0f);

    // Atualiza o watchdog apenas APÓS passar em todas as validações de segurança
    lastPacketTime = millis();

    // --- Pré-processamento do erro ---
    float erro = (fabsf(x_norm) < DEADZONE_CENTRO) ? 0.0f : x_norm;
    float erro_norm = constrain(erro / X_NORM_MAX_PRATICO, -1.0f, 1.0f);

    // --- Cálculo PID no espaço normalizado ---
    integral += erro_norm;
    integral  = constrain(integral, -MAX_INTEGRAL, MAX_INTEGRAL);  // Anti-windup

    float derivada   = erro_norm - erroAnterior;
    float pid_output = (Kp * erro_norm) + (Ki * integral) + (Kd * derivada);
    erroAnterior     = erro_norm;

    // --- Mixer de Tração Diferencial com clamping estrito de PWM ---
    int pwm_esquerdo = constrain((int)(base_pwm + pid_output), 0, 255);
    int pwm_direito  = constrain((int)(base_pwm - pid_output), 0, 255);

    ledcWrite(PIN_ENA, pwm_esquerdo);
    ledcWrite(PIN_ENB, pwm_direito);

    Serial.printf("X: %.3f | Norm: %.3f | PID: %.2f | PWM_E: %d | PWM_D: %d | Int: %.2f\n",
                  x_norm, erro_norm, pid_output, pwm_esquerdo, pwm_direito, integral);
}

// ---------------------------------------------------------------------------
// Reconexão MQTT não-bloqueante via máquina de estados
// ---------------------------------------------------------------------------
void handleReconnect() {
    if (client.connected()) {
        reconnectState = ReconnectState::IDLE;
        return;
    }

    unsigned long now = millis();

    switch (reconnectState) {
        case ReconnectState::IDLE:
            reconnectState       = ReconnectState::CONNECTING;
            reconnectLastAttempt = now;
            break;

        case ReconnectState::CONNECTING: {
            String clientId = "ESP32_Vision_";
            clientId += String(random(0xffff), HEX);

            Serial.print("Conectando ao Broker MQTT...");

            #if MQTT_USE_AUTH
              bool connected = client.connect(clientId.c_str(), MQTT_USER, MQTT_PASS);
            #else
              bool connected = client.connect(clientId.c_str());
            #endif

            if (connected) {
                Serial.println(" Conectado!");
                client.subscribe(topic_telemetry);
                reconnectState = ReconnectState::IDLE;
            } else {
                Serial.printf(" Falha (rc=%d). Aguardando %lums.\n",
                              client.state(), RECONNECT_INTERVAL);
                reconnectState       = ReconnectState::WAITING;
                reconnectLastAttempt = now;
            }
            break;
        }

        case ReconnectState::WAITING:
            if (now - reconnectLastAttempt >= RECONNECT_INTERVAL) {
                reconnectState = ReconnectState::CONNECTING;
            }
            break;
    }
}

// ---------------------------------------------------------------------------

void setup() {
    Serial.begin(115200);

    // Inicialização segura dos atuadores
    ledcAttach(PIN_ENA, PWM_FREQ, PWM_RESOLUTION);
    ledcAttach(PIN_ENB, PWM_FREQ, PWM_RESOLUTION);
    stopMotors();

    // Conexão Wi-Fi
    WiFi.begin(ssid, password);
    Serial.print("Conectando ao Wi-Fi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWi-Fi Conectado.");

    // Configuração de TLS e Broker MQTT
    #if MQTT_USE_TLS
      espClient.setCACert(ca_cert);
      Serial.println("TLS configurado com certificado CA.");
    #endif

    client.setServer(mqtt_server, mqtt_port);
    client.setCallback(mqttCallback);
    client.setBufferSize(MAX_PAYLOAD_SIZE + 64);
}

// ---------------------------------------------------------------------------

void loop() {
    if (!client.connected()) {
        stopMotors();
        handleReconnect();
    }

    client.loop();

    // Watchdog de Rede: desliga motores se o pacote MQTT não chegar dentro do timeout
    if (isTracking && (millis() - lastPacketTime > WATCHDOG_TIMEOUT)) {
        Serial.println("ALERTA: Watchdog desarmou os motores (Timeout de Rede)");
        stopMotors();
        integral     = 0.0f;
        erroAnterior = 0.0f;
        isTracking   = false;
    }
}
