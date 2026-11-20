"""
Testes de validação de payload MQTT — MQTTSender.

Cobre: valores válidos, clamping, NaN, Inf, tipos incorretos,
       publicação com mock, throttle e rejeição de payload inválido.
"""
import json
import time
import pytest
from unittest.mock import MagicMock, patch

from src.io.mqtt_sender import MQTTSender


# =============================================================================
# Validação estática (validate_telemetry)
# =============================================================================
class TestValidateTelemetry:

    def test_valid_centered(self):
        x, y, t = MQTTSender.validate_telemetry(0.0, 0.0, True)
        assert (x, y, t) == (0.0, 0.0, True)

    def test_valid_extremes(self):
        x, y, t = MQTTSender.validate_telemetry(1.0, -1.0, False)
        assert (x, y, t) == (1.0, -1.0, False)

    def test_clamp_x_positive(self):
        x, _, _ = MQTTSender.validate_telemetry(5.0, 0.0, True)
        assert x == 1.0

    def test_clamp_x_negative(self):
        x, _, _ = MQTTSender.validate_telemetry(-99.0, 0.0, True)
        assert x == -1.0

    def test_clamp_y_positive(self):
        _, y, _ = MQTTSender.validate_telemetry(0.0, 2.5, True)
        assert y == 1.0

    def test_clamp_y_negative(self):
        _, y, _ = MQTTSender.validate_telemetry(0.0, -2.5, True)
        assert y == -1.0

    def test_nan_x_raises(self):
        with pytest.raises(ValueError, match="NaN"):
            MQTTSender.validate_telemetry(float("nan"), 0.0, True)

    def test_nan_y_raises(self):
        with pytest.raises(ValueError, match="NaN"):
            MQTTSender.validate_telemetry(0.0, float("nan"), True)

    def test_inf_x_raises(self):
        with pytest.raises(ValueError, match="Infinito"):
            MQTTSender.validate_telemetry(float("inf"), 0.0, True)

    def test_neg_inf_y_raises(self):
        with pytest.raises(ValueError, match="Infinito"):
            MQTTSender.validate_telemetry(0.0, float("-inf"), True)

    def test_tracking_string_raises(self):
        with pytest.raises(ValueError, match="tracking"):
            MQTTSender.validate_telemetry(0.0, 0.0, "yes")

    def test_tracking_int_raises(self):
        with pytest.raises(ValueError, match="tracking"):
            MQTTSender.validate_telemetry(0.0, 0.0, 1)

    def test_x_string_raises(self):
        with pytest.raises(ValueError, match="numérico"):
            MQTTSender.validate_telemetry("0.5", 0.0, True)

    def test_x_none_raises(self):
        with pytest.raises(ValueError, match="numérico"):
            MQTTSender.validate_telemetry(None, 0.0, True)

    def test_x_bool_raises(self):
        with pytest.raises(ValueError, match="numérico"):
            MQTTSender.validate_telemetry(True, 0.0, True)

    def test_int_values_accepted(self):
        x, y, _ = MQTTSender.validate_telemetry(1, -1, True)
        assert isinstance(x, float)
        assert isinstance(y, float)
        assert (x, y) == (1.0, -1.0)

    def test_zero_tracking_false(self):
        _, _, t = MQTTSender.validate_telemetry(0.0, 0.0, False)
        assert t is False


# =============================================================================
# Envio completo com mock (send_telemetry)
# =============================================================================
class TestSendTelemetry:

    @pytest.fixture
    def sender(self):
        with patch("paho.mqtt.client.Client"):
            s = MQTTSender(broker="localhost", port=1883, topic="test/t")
            s.is_connected = True
            s._last_publish_time = 0.0
            return s

    def test_publish_valid_payload(self, sender):
        result_mock = MagicMock(rc=0)
        sender.client.publish = MagicMock(return_value=result_mock)

        sender.send_telemetry(0.5, -0.3, True)

        sender.client.publish.assert_called_once()
        payload = json.loads(sender.client.publish.call_args[0][1])
        assert payload == {"x": 0.5, "y": -0.3, "tracking": True}

    def test_reject_nan_no_publish(self, sender):
        sender.client.publish = MagicMock()
        sender.send_telemetry(float("nan"), 0.0, True)
        sender.client.publish.assert_not_called()

    def test_reject_when_disconnected(self, sender):
        sender.is_connected = False
        sender.client.publish = MagicMock()
        sender.send_telemetry(0.5, 0.0, True)
        sender.client.publish.assert_not_called()

    def test_throttle_rate(self, sender):
        result_mock = MagicMock(rc=0)
        sender.client.publish = MagicMock(return_value=result_mock)
        sender._min_publish_interval = 1.0
        sender._last_publish_time = time.perf_counter()

        sender.send_telemetry(0.5, 0.0, True)
        sender.client.publish.assert_not_called()

    def test_clamp_before_publish(self, sender):
        result_mock = MagicMock(rc=0)
        sender.client.publish = MagicMock(return_value=result_mock)

        sender.send_telemetry(5.0, -5.0, True)

        payload = json.loads(sender.client.publish.call_args[0][1])
        assert payload["x"] == 1.0
        assert payload["y"] == -1.0
