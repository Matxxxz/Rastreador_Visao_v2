import cv2
import numpy as np
import logging
import json
from pathlib import Path
from PySide6.QtCore import QThread, Signal, Qt, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel,
    QVBoxLayout, QHBoxLayout, QSlider, QGroupBox, QGridLayout, QPushButton
)

from src.vision.camera import CameraStream
from src.vision.processor import FrameProcessor
from config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = PROJECT_ROOT / "settings.json"


def _normalize_hsv_values(values, fallback):
    try:
        normalized = [int(v) for v in values]
    except (TypeError, ValueError):
        return list(fallback)

    if len(normalized) != 3:
        return list(fallback)

    limits = [(0, 179), (0, 255), (0, 255)]
    for i, (value, (min_value, max_value)) in enumerate(zip(normalized, limits)):
        normalized[i] = int(max(min_value, min(max_value, value)))

    return normalized


class VideoThread(QThread):
    change_pixmap_signal = Signal(np.ndarray, np.ndarray)
    telemetry_signal = Signal(int, int, int)  # FPS, X, Y

    def __init__(self):
        super().__init__()
        self._is_running = True
        self.cam = CameraStream()
        self.processor = FrameProcessor()

        self.hsv_lower = list(Config.HSV_LOWER)
        self.hsv_upper = list(Config.HSV_UPPER)

    def run(self):
        if not self.cam.connect():
            logging.error("Thread de vídeo abortada: Falha ao conectar na câmera.")
            self.telemetry_signal.emit(-1, -1, -1)
            return

        import time
        prev_time = time.time()

        while self._is_running:
            frame = self.cam.get_frame()
            if frame is None:
                logging.error("Thread de vídeo interrompida: câmera principal sem sinal.")
                self.telemetry_signal.emit(-1, -1, -1)
                break

            processed_frame, mask, centroid = self.processor.process(
                frame,
                hsv_lower=tuple(self.hsv_lower),
                hsv_upper=tuple(self.hsv_upper)
            )

            curr_time = time.time()
            fps = int(1.0 / (curr_time - prev_time)) if (curr_time - prev_time) > 0 else 0
            prev_time = curr_time

            x, y = centroid if centroid else (-1, -1)

            self.change_pixmap_signal.emit(processed_frame, mask)
            self.telemetry_signal.emit(fps, x, y)

        self.cam.release()

    def update_hsv(self, index: int, value: int, is_upper: bool):
        if is_upper:
            self.hsv_upper[index] = value
        else:
            self.hsv_lower[index] = value

    def stop(self):
        self._is_running = False
        self.cam.release()
        if not self.wait(1500):
            logging.warning("Thread de vídeo não encerrou dentro do tempo esperado.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vision Tracker V2 - Telemetria e Controle (PySide6)")
        self.setGeometry(100, 100, 1000, 600)

        self.thread = VideoThread()
        self.init_ui()

        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.telemetry_signal.connect(self.update_telemetry)

        self.thread.start()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        video_layout = QVBoxLayout()
        self.image_label = QLabel("Carregando Feed Principal...")
        self.mask_label = QLabel("Carregando Máscara...")

        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mask_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        video_layout.addWidget(self.image_label)
        video_layout.addWidget(self.mask_label)

        side_panel = QVBoxLayout()

        telemetry_group = QGroupBox("Telemetria em Tempo Real")
        telemetry_layout = QVBoxLayout()

        self.lbl_fps = QLabel("FPS: --")
        self.lbl_coords = QLabel("Coordenadas (X, Y): N/A")

        telemetry_layout.addWidget(self.lbl_fps)
        telemetry_layout.addWidget(self.lbl_coords)
        telemetry_group.setLayout(telemetry_layout)

        hsv_group = QGroupBox("Ajuste Fino de HSV")
        hsv_grid = QGridLayout()

        labels = ['H Min', 'S Min', 'V Min', 'H Max', 'S Max', 'V Max']
        self.sliders = []

        # Tenta carregar configurações salvas, faz fallback para o Config padrão se falhar
        loaded_lower = list(Config.HSV_LOWER)
        loaded_upper = list(Config.HSV_UPPER)

        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    loaded_lower = _normalize_hsv_values(data.get("hsv_lower", loaded_lower), Config.HSV_LOWER)
                    loaded_upper = _normalize_hsv_values(data.get("hsv_upper", loaded_upper), Config.HSV_UPPER)
            except Exception as e:
                logging.warning(f"Falha ao ler {SETTINGS_FILE}. Usando valores padrão. Erro: {e}")

        # Atualiza a thread com os valores carregados
        self.thread.hsv_lower = loaded_lower.copy()
        self.thread.hsv_upper = loaded_upper.copy()

        defaults = loaded_lower + loaded_upper
        max_values = [179, 255, 255, 179, 255, 255]

        for i in range(6):
            lbl = QLabel(f"{labels[i]}: {defaults[i]}")
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, max_values[i])
            slider.setValue(defaults[i])

            is_upper = i >= 3
            hsv_index = i % 3

            slider.valueChanged.connect(
                lambda val, idx=hsv_index, upper=is_upper, l=lbl, txt=labels[i]:
                self.on_slider_change(val, idx, upper, l, txt)
            )

            hsv_grid.addWidget(lbl, i, 0)
            hsv_grid.addWidget(slider, i, 1)
            self.sliders.append(slider)

        hsv_group.setLayout(hsv_grid)

        self.btn_reset = QPushButton("Limpar Trajetória")
        self.btn_reset.clicked.connect(self.reset_trajectory)

        side_panel.addWidget(telemetry_group)
        side_panel.addWidget(hsv_group)
        side_panel.addWidget(self.btn_reset)
        side_panel.addStretch()

        main_layout.addLayout(video_layout, stretch=2)
        main_layout.addLayout(side_panel, stretch=1)

    @Slot(np.ndarray, np.ndarray)
    def update_image(self, cv_img: np.ndarray, mask_img: np.ndarray):
        qt_img = self.convert_cv_to_qt(cv_img)
        qt_mask = self.convert_cv_to_qt(cv2.cvtColor(mask_img, cv2.COLOR_GRAY2BGR))

        self.image_label.setPixmap(QPixmap.fromImage(qt_img).scaled(480, 360, Qt.AspectRatioMode.KeepAspectRatio))
        self.mask_label.setPixmap(QPixmap.fromImage(qt_mask).scaled(480, 240, Qt.AspectRatioMode.KeepAspectRatio))

    def convert_cv_to_qt(self, cv_img: np.ndarray) -> QImage:
        rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_img.shape
        bytes_per_line = ch * w
        return QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

    @Slot(int, int, int)
    def update_telemetry(self, fps: int, x: int, y: int):
        if fps < 0:
            self.lbl_fps.setText("FPS: sem vídeo")
            self.lbl_coords.setText("Coordenadas: sem vídeo disponível")
            self.image_label.clear()
            self.mask_label.clear()
            self.image_label.setText("Sem vídeo disponível")
            self.mask_label.setText("Sem vídeo disponível")
            return

        self.lbl_fps.setText(f"FPS: {fps}")
        if x != -1 and y != -1:
            self.lbl_coords.setText(f"Coordenadas: X={x}, Y={y}")
        else:
            self.lbl_coords.setText("Coordenadas: Objeto não detectado")

    def on_slider_change(self, value: int, index: int, is_upper: bool, label: QLabel, text: str):
        label.setText(f"{text}: {value}")
        self.thread.update_hsv(index, value, is_upper)

    def reset_trajectory(self):
        self.thread.processor.reset_trajectory()

    def closeEvent(self, event):
        """Salva a calibração HSV no momento em que a janela é fechada e encerra a thread."""
        config_data = {
            "hsv_lower": self.thread.hsv_lower,
            "hsv_upper": self.thread.hsv_upper
        }
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(config_data, f, indent=4)
            logging.info("Calibração HSV salva com sucesso.")
        except Exception as e:
            logging.error(f"Erro ao salvar configurações: {e}")

        self.thread.stop()
        event.accept()