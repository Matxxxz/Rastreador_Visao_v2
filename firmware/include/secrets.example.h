// =============================================================================
// Credenciais de Rede e MQTT — Template
// =============================================================================
// INSTRUÇÕES:
//   1. Copie para secrets.h:  Copy-Item secrets.example.h secrets.h
//   2. Edite secrets.h com as credenciais do SEU ambiente.
//   3. NUNCA commite secrets.h — ele está no .gitignore.
// =============================================================================

#ifndef SECRETS_H
#define SECRETS_H

// --- Wi-Fi ---
#define WIFI_SSID       "NOME_DA_SUA_REDE"
#define WIFI_PASS       "SENHA_DA_SUA_REDE"

// --- Broker MQTT ---
#define MQTT_BROKER     "192.168.0.100"       // IP ou hostname do seu broker

// --- Autenticação MQTT (usado quando MQTT_USE_AUTH == 1) ---
#define MQTT_USER       "usuario_mqtt"
#define MQTT_PASS       "senha_mqtt"

#endif // SECRETS_H
