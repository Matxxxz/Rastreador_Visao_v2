"""
Fixtures globais para a suite de testes.

Se config.py não existir (CI / ambiente limpo), injeta um mock seguro
com todos os atributos esperados pelos módulos do projeto.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

# Adiciona a raiz do projeto ao sys.path para importação de módulos.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Mock seguro do config.py para ambientes sem configuração local.
if "config" not in sys.modules:
    try:
        import config  # noqa: F401
    except ImportError:
        sys.modules["config"] = SimpleNamespace(
            Config=SimpleNamespace(
                CAMERA_IP="http://127.0.0.1:8080/video",
                USE_IP_CAMERA=True,
                FRAME_WIDTH=640,
                FRAME_HEIGHT=480,
                HSV_LOWER=(89, 50, 50),
                HSV_UPPER=(130, 255, 255),
                MIN_CONTOUR_AREA=500,
                TRAJECTORY_MAX_POINTS=30,
                MQTT_BROKER="localhost",
                MQTT_PORT=1883,
                MQTT_TOPIC="test/telemetry",
                MQTT_USE_TLS=False,
                MQTT_CA_CERTS=None,
                MQTT_USERNAME=None,
                MQTT_PASSWORD=None,
                MQTT_MAX_PUBLISH_HZ=30.0,
            )
        )
