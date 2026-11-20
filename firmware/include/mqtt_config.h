#ifndef MQTT_CONFIG_H
#define MQTT_CONFIG_H

// =============================================================================
// Configuração Multi-Ambiente — Wi-Fi, MQTT e Segurança
// =============================================================================
// O ambiente ativo é selecionado por build_flags no platformio.ini:
//
//   [env:esp32dev]    → -DWOKWI_SIMULATION  (simulação, broker público, sem TLS)
//   [env:esp32local]  → -DLOCAL_DEV         (dev local, broker Mosquitto, sem TLS)
//   [env:esp32prod]   → -DPRODUCTION        (hardware real, TLS + autenticação)
//
// Para ambientes com credenciais reais (LOCAL_DEV, PRODUCTION), crie:
//   firmware/include/secrets.h   (baseado em secrets.example.h)
//   firmware/include/ca_cert.h   (baseado em ca_cert.example.h, só PRODUCTION)
//
// Ambos são ignorados pelo Git e NUNCA devem ser commitados.
// =============================================================================

// --- Limites de Payload MQTT ---
#define MAX_PAYLOAD_SIZE   256   // bytes máximos aceitos no callback
#define MQTT_KEEPALIVE     60    // segundos

// --- Tópico MQTT (pode ser sobrescrito via build_flags) ---
#ifndef MQTT_TOPIC_TELEMETRY
  #define MQTT_TOPIC_TELEMETRY "ufg/vision/telemetry"
#endif

// =============================================================================
// Seleção de Ambiente
// =============================================================================

#if defined(WOKWI_SIMULATION)
  // -------------------------------------------------------------------------
  // WOKWI: Rede virtual "Wokwi-GUEST" + broker público HiveMQ sem TLS.
  //         Seguro para simulação. NUNCA use em hardware real com atuadores.
  // -------------------------------------------------------------------------
  #define WIFI_SSID       "Wokwi-GUEST"
  #define WIFI_PASS       ""
  #define MQTT_BROKER     "broker.hivemq.com"
  #define MQTT_PORT       1883
  #define MQTT_USE_TLS    0
  #define MQTT_USE_AUTH   0

#elif defined(PRODUCTION)
  // -------------------------------------------------------------------------
  // PRODUÇÃO: TLS obrigatório + autenticação via secrets.h e ca_cert.h.
  // -------------------------------------------------------------------------
  #include "secrets.h"
  #include "ca_cert.h"
  #define MQTT_PORT       8883
  #define MQTT_USE_TLS    1
  #define MQTT_USE_AUTH   1

#elif defined(LOCAL_DEV)
  // -------------------------------------------------------------------------
  // DEV LOCAL: Broker Mosquitto na rede local, sem TLS para iteração rápida.
  //            Requer secrets.h com WIFI_SSID, WIFI_PASS e MQTT_BROKER.
  // -------------------------------------------------------------------------
  #include "secrets.h"
  #define MQTT_PORT       1883
  #define MQTT_USE_TLS    0
  #ifndef MQTT_USE_AUTH
    #define MQTT_USE_AUTH 0
  #endif

#else
  #error "Nenhum ambiente definido. Adicione -DWOKWI_SIMULATION, -DLOCAL_DEV ou -DPRODUCTION em build_flags."
#endif

#endif // MQTT_CONFIG_H
