# Política de Segurança

## Reportando Vulnerabilidades

Se você encontrar uma vulnerabilidade de segurança neste projeto, **NÃO** abra uma Issue pública.

Envie um relatório privado para o mantenedor através do perfil do GitHub: [@Matxxxz](https://github.com/Matxxxz).

### O que incluir no relatório

- Descrição da vulnerabilidade.
- Passos para reproduzir.
- Impacto potencial.
- Sugestão de correção (se houver).

### Tempo de resposta esperado

| Etapa | Prazo |
|---|---|
| Confirmação de recebimento | Até 72 horas |
| Avaliação inicial | Até 7 dias |
| Correção (se aplicável) | Variável conforme severidade |

## Práticas de Segurança do Projeto

### Configuração Sensível

- Credenciais, senhas, tokens e certificados **nunca** são commitados no Git.
- Arquivos sensíveis estão listados no `.gitignore`:
  `config.py`, `secrets.h`, `ca_cert.h`, `*.pem`, `*.key`, `.env`, `settings.json`.
- Templates seguros estão disponíveis:
  - `config.example.py` — configuração do host Python.
  - `firmware/include/secrets.example.h` — credenciais Wi-Fi e MQTT.
  - `firmware/include/ca_cert.example.h` — certificado CA do broker.

### MQTT

- **Simulação (Wokwi):** Broker público HiveMQ sem TLS — **apenas para testes**.
- **Produção:** TLS obrigatório (porta 8883), autenticação e certificado CA válido.
- O payload MQTT é validado (tipo, faixa, NaN/Inf) antes de afetar atuadores.
- O tópico de telemetria é verificado no callback do firmware.

### Firmware

- Watchdog de rede de 500 ms desliga motores em caso de perda de conexão.
- Controlador PID com anti-windup e clamping em todas as saídas PWM.
- JSON inválido, campos ausentes ou valores fora de faixa são rejeitados.
- Fail-safe: motores param em qualquer condição de erro de rede ou payload.

## Versões Suportadas

| Versão | Suporte |
|---|---|
| `main` (HEAD) | ✅ Correções de segurança aceitas |
| Commits anteriores | ❌ Sem suporte retroativo |
