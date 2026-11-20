import json
import logging
import math
import time
from typing import Optional, Tuple
import paho.mqtt.client as mqtt


class MQTTSender:
    """
    Cliente MQTT assíncrono para publicação de telemetria de visão.

    Suporta:
      - Simulação (broker HiveMQ público, sem TLS)
      - Desenvolvimento local (broker Mosquitto LAN)
      - Produção (TLS com verificação estrita de CA + autenticação)
      - Validação estrita de payload (rejeição de NaN/Inf/tipos incorretos + clamping)
      - Throttle de taxa (default 30 Hz) e limitação de fila
    """

    @staticmethod
    def validate_telemetry(x: float, y: float, is_tracking: bool) -> Tuple[float, float, bool]:
        """
        Valida e normaliza as coordenadas de telemetria antes da publicação.

        Lança:
            ValueError: Se os tipos forem incorretos, ou se contiverem NaN ou Infinito.
        Retorna:
            (clamped_x, clamped_y, is_tracking) com x, y no intervalo [-1.0, 1.0].
        """
        if type(is_tracking) is not bool:
            raise ValueError(f"O campo 'tracking' deve ser bool (True/False), recebido {type(is_tracking).__name__}.")

        for name, val in [("x", x), ("y", y)]:
            if type(val) not in (int, float):
                raise ValueError(f"O campo '{name}' deve ter valor numérico, recebido {type(val).__name__}.")
            if math.isnan(val):
                raise ValueError(f"O campo '{name}' contém valor inválido: NaN.")
            if math.isinf(val):
                raise ValueError(f"O campo '{name}' contém valor inválido: Infinito.")

        clamped_x = max(-1.0, min(1.0, float(x)))
        clamped_y = max(-1.0, min(1.0, float(y)))
        return clamped_x, clamped_y, is_tracking

    def __init__(
            self,
            broker: Optional[str] = None,
            port: Optional[int] = None,
            topic: Optional[str] = None,
            use_tls: Optional[bool] = None,
            ca_certs: Optional[str] = None,
            username: Optional[str] = None,
            password: Optional[str] = None,
            max_publish_hz: Optional[float] = None,
    ):
        # Tenta carregar do config.py se existir; caso contrário usa defaults seguros de simulação
        try:
            from config import Config
        except ImportError:
            Config = None

        self.broker = broker if broker is not None else getattr(Config, "MQTT_BROKER", "broker.hivemq.com")
        self.port = port if port is not None else getattr(Config, "MQTT_PORT", 1883)
        self.topic = topic if topic is not None else getattr(Config, "MQTT_TOPIC", "ufg/vision/telemetry")
        self.use_tls = use_tls if use_tls is not None else getattr(Config, "MQTT_USE_TLS", False)
        self.ca_certs = ca_certs if ca_certs is not None else getattr(Config, "MQTT_CA_CERTS", None)
        self.username = username if username is not None else getattr(Config, "MQTT_USERNAME", None)
        self.password = password if password is not None else getattr(Config, "MQTT_PASSWORD", None)

        hz = max_publish_hz if max_publish_hz is not None else getattr(Config, "MQTT_MAX_PUBLISH_HZ", 30.0)

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.max_queued_messages_set(120)
        self.client.max_inflight_messages_set(20)
        self.is_connected = False
        self._last_publish_time = 0.0
        self._min_publish_interval = 1.0 / max(1.0, hz)

        # Autenticação segura — credenciais nunca são impressas em logs
        if self.username:
            self.client.username_pw_set(self.username, self.password)
            logging.info("MQTT: Autenticação de usuário configurada.")

        # TLS com verificação estrita de certificados
        if self.use_tls:
            import ssl
            self.client.tls_set(
                ca_certs=self.ca_certs,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT
            )
            self.client.tls_insecure_set(False)
            logging.info("MQTT: TLS 8883 ativado com verificação estrita de CA.")

    def connect(self):
        try:
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.connect_async(self.broker, self.port, keepalive=60)
            self.client.loop_start()  # Thread dedicada de I/O de rede
        except Exception as e:
            logging.error(f"Falha ao inicializar cliente MQTT: {e}")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.is_connected = True
            logging.info(f"Conectado com sucesso ao Broker MQTT: {self.broker}:{self.port}")
        else:
            logging.error(f"Falha na conexão MQTT. Código de retorno: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.is_connected = False
        logging.warning(f"Desconectado do Broker MQTT. Código: {reason_code}")

    def send_telemetry(self, x_norm: float, y_norm: float, is_tracking: bool):
        if not self.is_connected:
            return

        now = time.perf_counter()
        if (now - self._last_publish_time) < self._min_publish_interval:
            return

        try:
            cx, cy, ct = self.validate_telemetry(x_norm, y_norm, is_tracking)
        except ValueError as err:
            logging.warning(f"MQTT: Telemetria descartada por validação: {err}")
            return

        self._last_publish_time = now

        payload = {
            "x": round(cx, 3),
            "y": round(cy, 3),
            "tracking": ct
        }

        # QoS 0 para telemetria contínua a 30 Hz (baixa latência, descarta pacotes antigos).
        # Retain=False obrigatório: o nó receptor deve agir apenas em dados frescos.
        result = self.client.publish(self.topic, json.dumps(payload), qos=0, retain=False)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logging.error(f"Falha no envio MQTT (rc={result.rc})")

    def disconnect(self):
        self.client.disconnect()
        self.client.loop_stop()
        logging.info("Serviço MQTT encerrado.")
