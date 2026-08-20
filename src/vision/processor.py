import cv2
import numpy as np
import logging
from collections import deque
from typing import Tuple, Optional
from config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class FrameProcessor:
    def __init__(self):
        # Fila circular para o rastro da trajetória (evita consumo descontrolado de RAM)
        self.trajectory = deque(maxlen=Config.TRAJECTORY_MAX_POINTS)

    def process(
            self,
            frame: Optional[np.ndarray],
            hsv_lower: Tuple[int, int, int] = Config.HSV_LOWER,
            hsv_upper: Tuple[int, int, int] = Config.HSV_UPPER
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[Tuple[int, int]]]:
        """ Processa o frame recebido e retorna:
        - processed_frame: Frame original desenhado com contornos, centroide e rastro.
        - mask: Máscara binária resultante da segmentação por cor.
        - centroid: Tupla (X, Y) do objeto ou None caso nada seja detectado. """

        if frame is None:
            return None, None, None

        normalized_lower = []
        normalized_upper = []
        hsv_limits = ((0, 179), (0, 255), (0, 255))

        for lower_value, upper_value, (min_value, max_value) in zip(hsv_lower, hsv_upper, hsv_limits):
            lower_value = int(max(min_value, min(max_value, lower_value)))
            upper_value = int(max(min_value, min(max_value, upper_value)))

            if lower_value > upper_value:
                lower_value, upper_value = upper_value, lower_value

            normalized_lower.append(lower_value)
            normalized_upper.append(upper_value)

        # 1. Filtro Gaussiano para atenuação de ruído (Kernel 11x11)
        blurred = cv2.GaussianBlur(frame, (11, 11), 0)

        # 2. Conversão para o Espaço de Cores HSV
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

        # 3. Limiarização por cor (Gera imagem binária)
        mask = cv2.inRange(hsv, np.array(normalized_lower), np.array(normalized_upper))

        # 4. Operações morfológicas para remoção de ruídos residuais
        morph_kernel = np.ones((3, 3), np.uint8)
        mask = cv2.erode(mask, morph_kernel, iterations=2)
        mask = cv2.dilate(mask, morph_kernel, iterations=2)

        # 5. Detecção de contornos na máscara
        contours, _ = cv2.findContours(
            mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        centroid = None

        # Processa apenas se houver pelo menos um contorno válido
        if len(contours) > 0:
            # Seleciona o maior contorno com base na área
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)

            # Aplica o threshold de área mínima definida no config
            if area > Config.MIN_CONTOUR_AREA:
                # Cálculo dos momentos de massa
                moments = cv2.moments(largest_contour)

                if moments["m00"] != 0:
                    center_x = int(moments["m10"] / moments["m00"])
                    center_y = int(moments["m01"] / moments["m00"])
                    centroid = (center_x, center_y)

                    # Desenha o círculo delimitador e o centroide no frame original
                    ((x, y), radius) = cv2.minEnclosingCircle(largest_contour)
                    cv2.circle(frame, (int(x), int(y)), int(radius), (0, 255, 255), 2)
                    cv2.circle(frame, centroid, 5, (0, 0, 255), -1)

        # 6. Atualiza o rastro da trajetória
        self.trajectory.appendleft(centroid)

        # Desenha o rastro contínuo com atenuação de espessura
        for i in range(1, len(self.trajectory)):
            if self.trajectory[i - 1] is None or self.trajectory[i] is None:
                continue

            # Espessura regressiva ao longo do tempo do ponto
            thickness = int(np.sqrt(Config.TRAJECTORY_MAX_POINTS / float(i + 1)) * 2.5)
            cv2.line(frame, self.trajectory[i - 1], self.trajectory[i], (0, 0, 255), thickness)

        return frame, mask, centroid

    def reset_trajectory(self):
        """Limpa o histórico do rastro armazenado em memória."""
        self.trajectory.clear()