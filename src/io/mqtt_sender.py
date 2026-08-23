import json
import logging
import time
import paho.mqtt.client as mqtt


class MQTTSender:
    def __init__(
            self,
            broker: str = "broker.hivemq.com",
            port: int = 1883,
            topic: str = "ufg/vision/telemetry",
            max_publish_hz: float = 30.0,
    ):
        """
        Para testes sem hardware local, usamos o broker público e gratuito HiveMQ.
        Com o ESP32 físico, basta alterar o 'broker' para o IP da sua máquina local.
        """
        self.broker = broker
        self.port = port
        self.topic = topic
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.max_queued_messages_set(120)
        self.client.max_inflight_messages_set(20)
        self.is_connected = False
        self._last_publish_time = 0.0
        self._min_publish_interval = 1.0 / max(1.0, max_publish_hz)

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
            logging.info(f"Conectado com sucesso ao Broker MQTT: {self.broker}")
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
        self._last_publish_time = now

        payload = {
            "x": round(x_norm, 3),
            "y": round(y_norm, 3),
            "tracking": is_tracking
        }

        result = self.client.publish(self.topic, json.dumps(payload), qos=0)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logging.error(f"Falha no envio MQTT (rc={result.rc})")

    def disconnect(self):
        self.client.disconnect()
        self.client.loop_stop()
        logging.info("Serviço MQTT encerrado.")