import cv2
import logging
import threading
from config import Config

class CameraStream:
    def __init__(self):
        self.cap = None
        self.is_running = False
        self._lock = threading.RLock()

    def connect(self) -> bool:
        """
        Tenta conectar apenas à câmera principal configurada.
        Em caso de falha, aplica fail-fast e não assume outra fonte de vídeo.
        """
        if not Config.USE_IP_CAMERA or not Config.CAMERA_IP:
            logging.error("Erro Crítico: câmera principal desativada ou sem endereço configurado.")
            return False

        with self._lock:
            self.release()
            try:
                logging.info(f"Tentando conectar à Câmera IP: {Config.CAMERA_IP}")
                self.cap = cv2.VideoCapture(Config.CAMERA_IP)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not self.cap.isOpened():
                    raise ConnectionError("Falha crítica ao abrir a Câmera IP.")

                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.FRAME_WIDTH)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.FRAME_HEIGHT)

                ret, frame = self.cap.read()
                if not ret or frame is None:
                    raise ConnectionError("Câmera IP abriu, mas não entregou frame inicial.")

                self.is_running = True
                logging.info("Câmera estabilizada e conectada com sucesso.")
                return True
            except Exception as e:
                logging.error(f"Erro Crítico ao conectar na câmera principal: {e}")
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None
                self.is_running = False
                return False

    def get_frame(self):
        """
        Lê o buffer de vídeo e retorna um frame.
        Retorna numpy.ndarray se sucesso, ou None se falhar.
        """
        with self._lock:
            if not self.is_running or self.cap is None:
                return None

            try:
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    logging.error("Erro Crítico: falha ao ler frame da câmera principal.")
                    self.release()
                    return None
                return frame
            except Exception as e:
                logging.error(f"Erro Crítico durante a leitura do frame: {e}")
                self.release()
                return None

    def release(self):
        """Destrutor seguro: limpa a memória alocada pelo OpenCV."""
        with self._lock:
            self.is_running = False
            if self.cap is not None:
                self.cap.release()
                self.cap = None
                logging.info("Recursos de hardware liberados.")
