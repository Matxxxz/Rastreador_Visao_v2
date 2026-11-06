#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// Guard de compatibilidade: este firmware usa a API ledc do Arduino ESP32 Core 3.x.
// ledcAttach(pin, freq, resolution) e ledcWrite(pin, duty) foram introduzidos no Core 3.0.
// Se você ver um erro "ledcAttach was not declared in this scope", verifique se
// platform_packages em platformio.ini aponta para o Core 3.x (>= 3.0.0).
// Versão do Core em uso: ESP_ARDUINO_VERSION_MAJOR deve ser >= 3.
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR < 3
  #error "Este firmware requer Arduino ESP32 Core >= 3.0.0. Atualize platform_packages no platformio.ini."
#endif

const char* ssid            = "Wokwi-GUEST";
const char* password        = "";
const char* mqtt_server     = "broker.hivemq.com";
const char* topic_telemetry = "ufg/vision/telemetry";

WiFiClient   espClient;
PubSubClient client(espClient);

// --- Pinos de PWM ---
// FIX [P1-1]: API ledcSetup/ledcAttachPin depreciada no Arduino Core 3.x / ESP-IDF 5.x.
// A nova API usa ledcAttach(pin, freq, resolution) diretamente no pino, sem canal explícito.
// ledcWrite(pin, duty) também opera sobre o pino, não sobre o canal numérico.
const int PIN_ENA = 25;  // Motor Esquerdo (LED Vermelho no Wokwi)
const int PIN_ENB = 14;  // Motor Direito  (LED Azul no Wokwi)
const int PWM_FREQ       = 5000;  // Hz
const int PWM_RESOLUTION = 8;     // bits → duty de 0 a 255

// --- Watchdog de Rede ---
unsigned long lastPacketTime    = 0;
const unsigned long WATCHDOG_TIMEOUT = 500;  // ms
bool isTracking = false;

// --- Controle PID (Tração Diferencial) ---
float Kp       = 100.0f;
float Ki       = 0.0f;   // Mantido em 0 até sintonia fina no hardware físico
float Kd       = 0.0f;
float erroAnterior = 0.0f;
float integral     = 0.0f;
int   base_pwm     = 150;

// FIX [P1-3]: Limite de clamping do acumulador integral (anti-windup).
// Impede crescimento ilimitado quando Ki > 0 for ativado no hardware físico.
// Valor calculado para que Ki * MAX_INTEGRAL não ultrapasse o range de saída PID (±255).
// Com Ki = 1.0, limita a contribuição integral a ±127 (metade do range PWM).
const float MAX_INTEGRAL = 127.0f;

// --- Estado da máquina de reconexão MQTT não-bloqueante ---
// FIX [P1-2]: reconnect() com while+delay(5000) bloqueava o loop principal,
// impedindo o watchdog de disparar durante uma queda de rede com motores ativos.
// Substituído por uma máquina de estados controlada por millis().
enum class ReconnectState { IDLE, CONNECTING, WAITING };
ReconnectState reconnectState       = ReconnectState::IDLE;
unsigned long  reconnectLastAttempt = 0;
const unsigned long RECONNECT_INTERVAL = 5000;  // ms entre tentativas

// ---------------------------------------------------------------------------

void stopMotors() {
    // FIX [P1-1]: ledcWrite agora recebe o pino diretamente (Core 3.x).
    ledcWrite(PIN_ENA, 0);
    ledcWrite(PIN_ENB, 0);
}

// ---------------------------------------------------------------------------
// Callback MQTT: chamado pela thread do PubSubClient ao receber pacote.
// Responsabilidade: deserializar JSON, atualizar estado e calcular PID.
// ---------------------------------------------------------------------------
void mqttCallback(char* topic, byte* payload, unsigned int length) {
    lastPacketTime = millis();

    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, payload, length);

    if (error) {
        Serial.println("Erro: Falha na desserializacao do JSON");
        return;
    }

    isTracking = doc["tracking"].as<bool>();
    if (!isTracking) {
        stopMotors();
        // Reseta o acumulador integral para evitar windup acumulado durante parada.
        integral       = 0.0f;
        erroAnterior   = 0.0f;
        Serial.println("Alvo perdido. Motores parados. Integral resetada.");
        return;
    }

    float x_norm = doc["x"].as<float>();

    // --- Cálculo PID ---
    float erro    = x_norm;
    integral     += erro;

    // FIX [P1-3]: Anti-windup por clamping — limita o acumulador ao intervalo
    // [-MAX_INTEGRAL, +MAX_INTEGRAL] antes de multiplicar por Ki.
    // Essencial para evitar ganho de integral descontrolado na transição Wokwi → hardware físico.
    integral = constrain(integral, -MAX_INTEGRAL, MAX_INTEGRAL);

    float derivada   = erro - erroAnterior;
    float pid_output = (Kp * erro) + (Ki * integral) + (Kd * derivada);
    erroAnterior     = erro;

    // --- Mapeamento para tração diferencial ---
    int pwm_esquerdo = constrain((int)(base_pwm + pid_output), 0, 255);
    int pwm_direito  = constrain((int)(base_pwm - pid_output), 0, 255);

    // FIX [P1-1]: ledcWrite com pino (Core 3.x).
    ledcWrite(PIN_ENA, pwm_esquerdo);
    ledcWrite(PIN_ENB, pwm_direito);

    Serial.printf("X: %.3f | PID: %.2f | PWM_E: %d | PWM_D: %d | Integral: %.2f\n",
                  x_norm, pid_output, pwm_esquerdo, pwm_direito, integral);
}

// ---------------------------------------------------------------------------
// FIX [P1-2]: Lógica de reconexão não-bloqueante (máquina de estados + millis).
// Deve ser chamada a cada iteração do loop(). Nunca usa delay() nem while().
// O loop principal — e portanto o watchdog — continua executando normalmente
// durante toda a janela de espera entre tentativas de reconexão.
// ---------------------------------------------------------------------------
void handleReconnect() {
    if (client.connected()) {
        reconnectState = ReconnectState::IDLE;
        return;
    }

    unsigned long now = millis();

    switch (reconnectState) {
        case ReconnectState::IDLE:
            // Inicia a primeira tentativa imediatamente.
            reconnectState       = ReconnectState::CONNECTING;
            reconnectLastAttempt = now;
            break;

        case ReconnectState::CONNECTING: {
            String clientId = "ESP32_Vision_";
            clientId += String(random(0xffff), HEX);

            Serial.print("Conectando ao Broker MQTT...");
            if (client.connect(clientId.c_str())) {
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
                // Intervalo de backoff expirou: tenta novamente.
                reconnectState = ReconnectState::CONNECTING;
            }
            break;
    }
}

// ---------------------------------------------------------------------------

void setup() {
    Serial.begin(115200);

    // FIX [P1-1]: Nova API de PWM do Arduino Core 3.x.
    // ledcAttach(pin, freq_hz, resolution_bits) substitui ledcSetup + ledcAttachPin.
    ledcAttach(PIN_ENA, PWM_FREQ, PWM_RESOLUTION);
    ledcAttach(PIN_ENB, PWM_FREQ, PWM_RESOLUTION);

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

// ---------------------------------------------------------------------------

void loop() {
    // FIX [P1-2]: handleReconnect() substitui o bloco bloqueante reconnect().
    // Garante que o watchdog abaixo seja verificado em TODA iteração do loop,
    // inclusive durante o backoff de 5s entre tentativas de conexão ao broker.
    if (!client.connected()) {
        stopMotors();
        handleReconnect();
    }

    client.loop();

    // --- Watchdog de Segurança ---
    // Desamar motores se o pacote MQTT não chegar dentro do timeout.
    if (isTracking && (millis() - lastPacketTime > WATCHDOG_TIMEOUT)) {
        Serial.println("ALERTA: Watchdog desarmou os motores (Timeout de Rede)");
        stopMotors();
        integral     = 0.0f;
        erroAnterior = 0.0f;
        isTracking   = false;
    }
}
