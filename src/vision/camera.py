import cv2
import logging
from config import Config

# Configuração de logging (substitui prints amadores e facilita debug)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class CameraStream:
    def __init__(self):
        self.cap = None
        self.is_running = False

    def connect(self) -> bool:
        """
        Tenta conectar à câmera IP. Se falhar ou estiver desativado,
        faz o fallback automático para a webcam local.
        """
        try:
            if Config.USE_IP_CAMERA and Config.CAMERA_IP:
                logging.info(f"Tentando conectar à Câmera IP: {Config.CAMERA_IP}")
                self.cap = cv2.VideoCapture(Config.CAMERA_IP)
                # FORÇA O OPENCV A NÃO FAZER BUFFERING DA REDE (Crucial para diminuir latência)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            else:
                raise ValueError("Uso de câmera IP desativado na configuração ou IP ausente.")

            # Verifica se o frame pode ser lido (conexão bem-sucedida)
            if not self.cap.isOpened():
                raise ConnectionError("Falha de rede ao abrir a Câmera IP.")

        except (ValueError, ConnectionError) as e:
            logging.warning(f"{e} Iniciando fallback para Webcam (Index {Config.FALLBACK_CAMERA_INDEX}).")
            self.cap = cv2.VideoCapture(Config.FALLBACK_CAMERA_INDEX)

        # Validação final do Fallback
        if not self.cap or not self.cap.isOpened():
            logging.error("Erro Crítico: Nenhuma fonte de vídeo (IP ou Webcam) disponível.")
            return False

        # Configura a resolução via API do OpenCV
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.FRAME_HEIGHT)

        self.is_running = True
        logging.info("Câmera estabilizada e conectada com sucesso.")
        return True

    def get_frame(self):
        """
        Lê o buffer de vídeo e retorna um frame.
        Retorna numpy.ndarray se sucesso, ou None se falhar.
        """
        if not self.is_running or self.cap is None:
            return None

        try:
            ret, frame = self.cap.read()
            if not ret:
                logging.warning("Frame descartado/corrompido. Câmera desconectada?")
                return None
            return frame
        except Exception as e:
            logging.error(f"Exceção durante a leitura do frame: {e}")
            return None

    def release(self):
        """Destrutor seguro: limpa a memória alocada pelo OpenCV."""
        self.is_running = False
        if self.cap is not None:
            self.cap.release()
            logging.info("Recursos de hardware liberados.")