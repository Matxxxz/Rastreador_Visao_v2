"""
Configuração LOCAL do host Python — NÃO commitado no Git.

Instruções:
  1. Copie para 'config.py':  Copy-Item config.example.py config.py
  2. Edite config.py com os valores do SEU ambiente.
  3. NUNCA commite config.py — ele está no .gitignore.
"""


class Config:
    # =====================================================================
    # Vídeo — Fonte de Captura
    # =====================================================================
    CAMERA_IP = "http://192.168.0.X:8080/video"  # ← substitua pelo IP real
    USE_IP_CAMERA = True

    FRAME_WIDTH = 640
    FRAME_HEIGHT = 480

    # =====================================================================
    # Intervalos de Cor HSV (Azul padrão para testes)
    # =====================================================================
    HSV_LOWER = (89, 50, 50)
    HSV_UPPER = (130, 255, 255)

    # =====================================================================
    # Filtros Geométricos
    # =====================================================================
    MIN_CONTOUR_AREA = 500
    TRAJECTORY_MAX_POINTS = 30

    # =====================================================================
    # MQTT — Comunicação com o Broker
    # =====================================================================
    # SIMULAÇÃO (broker público, sem TLS — apenas para Wokwi/testes):
    #   MQTT_BROKER = "broker.hivemq.com"
    #   MQTT_PORT = 1883
    #   MQTT_USE_TLS = False
    #
    # HARDWARE REAL (broker local Mosquitto, com TLS):
    #   MQTT_BROKER = "192.168.0.100"
    #   MQTT_PORT = 8883
    #   MQTT_USE_TLS = True
    #   MQTT_CA_CERTS = "certs/ca.crt"
    #   MQTT_USERNAME = "seu_usuario"
    #   MQTT_PASSWORD = "sua_senha"

    MQTT_BROKER = "broker.hivemq.com"
    MQTT_PORT = 1883
    MQTT_TOPIC = "ufg/vision/telemetry"
    MQTT_USE_TLS = False
    MQTT_CA_CERTS = None
    MQTT_USERNAME = None
    MQTT_PASSWORD = None
    MQTT_MAX_PUBLISH_HZ = 30.0
