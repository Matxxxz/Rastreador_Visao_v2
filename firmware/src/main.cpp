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
float Kp           = 120.0f;  // Ganho proporcional — calibrar na bancada física
float Ki           = 0.0f;    // Mantido em 0 até sintonia fina no hardware real
float Kd           = 0.0f;    // Mantido em 0 até sintonia fina no hardware real
float erroAnterior = 0.0f;
float integral     = 0.0f;
int   base_pwm     = 120;     // Velocidade base de ambos os motores em rastreamento reto

// Anti-windup: teto do acumulador integral (ativo quando Ki > 0).
// Com Ki = 1.0, a contribuição integral fica limitada a ±127 (metade do range PWM).
const float MAX_INTEGRAL = 127.0f;

// --- Normalização do sensor de visão ---
// O pipeline Python normaliza o centroide para [-1.0, +1.0], mas na prática
// a câmera IP nunca entrega |x_norm| = 1.0: o valor máximo observado nas bordas
// do enquadramento é ~0.74 (limitação do campo de visão + calibração HSV).
//
// Problema sem normalização (base_pwm=120, Kp=120, x_max=0.74):
//   pid_output = 120 × 0.74 = 88.8
//   pwm_interno = 120 − 88.8 = 31.2  →  nunca atinge 0, LED oposto nunca apaga.
//
// Solução: normalizar o erro pelo máximo prático antes do PID.
//   erro_norm = x_norm / X_NORM_MAX_PRATICO
//   Com x_norm = 0.74 → erro_norm = 1.0 → pid_output = Kp = 120
//   pwm_interno = 120 − 120 = 0  ✓  LED apaga completamente.
//
// X_NORM_MAX_PRATICO: ajuste este valor se trocar de câmera ou resolução.
const float X_NORM_MAX_PRATICO = 0.74f;

// Zona-morta central: suprime micro-correções quando o alvo está quase centrado.
// Evita oscilação de PWM residual e zumbido nos motores durante rastreamento estável.
// Unidade: fração do erro normalizado (0.0 = desativado).
const float DEADZONE_CENTRO = 0.05f;

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

    JsonDocument doc;
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

    // --- Pré-processamento do erro ---

    // 1. Zona-morta central: suprime ação do controlador quando o alvo está praticamente
    //    centrado. Evita micro-oscilações de PWM que causam zumbido nos motores físicos.
    float erro = (fabsf(x_norm) < DEADZONE_CENTRO) ? 0.0f : x_norm;

    // 2. Normalização pelo máximo prático do sensor:
    //    Mapeia [−X_NORM_MAX_PRATICO, +X_NORM_MAX_PRATICO] → [−1.0, +1.0].
    //    Garante que a borda real da câmera produza erro unitário para o PID,
    //    permitindo que pid_output alcance exatamente ±Kp e zere o motor oposto.
    float erro_norm = constrain(erro / X_NORM_MAX_PRATICO, -1.0f, 1.0f);

    // --- Cálculo PID no espaço normalizado ---
    integral += erro_norm;
    integral  = constrain(integral, -MAX_INTEGRAL, MAX_INTEGRAL);  // Anti-windup

    float derivada   = erro_norm - erroAnterior;
    float pid_output = (Kp * erro_norm) + (Ki * integral) + (Kd * derivada);
    erroAnterior     = erro_norm;

    // --- Mixer de Tração Diferencial ---
    // Ambos os motores partem de base_pwm (marcha reta).
    // pid_output desloca PWM para cima em um lado e para baixo no outro.
    //
    // Garantia matemática após normalização:
    //   pid_output_max = Kp × 1.0 = 120
    //   pwm_min        = base_pwm − Kp = 120 − 120 = 0  ✓
    //   pwm_max        = base_pwm + Kp = 120 + 120 = 240 (dentro de [0, 255]) ✓
    //
    // constrain() protege contra extrapolação caso Ki ou Kd adicionem overshoot.
    int pwm_esquerdo = constrain((int)(base_pwm + pid_output), 0, 255);
    int pwm_direito  = constrain((int)(base_pwm - pid_output), 0, 255);

    ledcWrite(PIN_ENA, pwm_esquerdo);
    ledcWrite(PIN_ENB, pwm_direito);

    Serial.printf("X: %.3f | Norm: %.3f | PID: %.2f | PWM_E: %d | PWM_D: %d | Int: %.2f\n",
                  x_norm, erro_norm, pid_output, pwm_esquerdo, pwm_direito, integral);
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
