// =============================================================================
// Certificado CA do Broker MQTT — Template
// =============================================================================
// INSTRUÇÕES:
//   1. Copie para ca_cert.h:  Copy-Item ca_cert.example.h ca_cert.h
//   2. Substitua pelo certificado CA real do seu broker MQTT.
//      Para Mosquitto local: cat /etc/mosquitto/certs/ca.crt
//   3. Cada linha do PEM deve terminar com \n" \
//   4. NUNCA commite ca_cert.h — ele está no .gitignore.
// =============================================================================

#ifndef CA_CERT_H
#define CA_CERT_H

const char* ca_cert = \
"-----BEGIN CERTIFICATE-----\n" \
"SUBSTITUA_ESTE_BLOCO_PELO_CERTIFICADO_CA_REAL\n" \
"DO_SEU_BROKER_MQTT_LINHA_A_LINHA\n" \
"-----END CERTIFICATE-----\n";

#endif // CA_CERT_H
