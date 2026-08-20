import cv2
import numpy as np
import logging
from collections import deque
from typing import Tuple, Optional
from config import Config
from src.vision.kalman import KalmanTracker

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FrameProcessor:
    def __init__(self):
        self.trajectory = deque(maxlen=Config.TRAJECTORY_MAX_POINTS)
        self.kalman = KalmanTracker()
        self.lost_frames = 0
        self.max_lost_frames = 15  # TTL: Limite de frames para confiar na inércia sem vídeo

    def process(
            self,
            frame: Optional[np.ndarray],
            hsv_lower: Tuple[int, int, int] = Config.HSV_LOWER,
            hsv_upper: Tuple[int, int, int] = Config.HSV_UPPER
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[Tuple[int, int]]]:

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

        blurred = cv2.GaussianBlur(frame, (11, 11), 0)
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(normalized_lower), np.array(normalized_upper))

        morph_kernel = np.ones((3, 3), np.uint8)
        mask = cv2.erode(mask, morph_kernel, iterations=2)
        mask = cv2.dilate(mask, morph_kernel, iterations=2)

        contours, _ = cv2.findContours(
            mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        measured_centroid = None
        predicted_centroid = self.kalman.predict()

        if len(contours) > 0:
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)

            if area > Config.MIN_CONTOUR_AREA:
                moments = cv2.moments(largest_contour)

                if moments["m00"] != 0:
                    center_x = int(moments["m10"] / moments["m00"])
                    center_y = int(moments["m01"] / moments["m00"])
                    measured_centroid = (center_x, center_y)

                    self.kalman.correct(center_x, center_y)
                    self.lost_frames = 0  # Reseta o contador de perda

                    ((x, y), radius) = cv2.minEnclosingCircle(largest_contour)
                    cv2.circle(frame, (int(x), int(y)), int(radius), (0, 255, 255), 2)

        # Lógica de TTL (Time-To-Live) para a previsão matemática
        if measured_centroid is None:
            self.lost_frames += 1

        if self.lost_frames > self.max_lost_frames:
            final_centroid = None  # Aborta rastreamento fantasma
        else:
            final_centroid = measured_centroid if measured_centroid else predicted_centroid

        # Renderização Camada 1: Rastro da Trajetória (Azul)
        if final_centroid and final_centroid != (0, 0):
            self.trajectory.appendleft(final_centroid)

        for i in range(1, len(self.trajectory)):
            if self.trajectory[i - 1] is None or self.trajectory[i] is None:
                continue
            thickness = int(np.sqrt(Config.TRAJECTORY_MAX_POINTS / float(i + 1)) * 2.5)
            cv2.line(frame, self.trajectory[i - 1], self.trajectory[i], (255, 0, 0), thickness)

        # Renderização Camada 2: Centroides sobrepostos ao rastro
        if final_centroid and final_centroid != (0, 0):
            if measured_centroid:
                # Alvo Confirmado na Câmera -> PONTO VERMELHO
                cv2.circle(frame, measured_centroid, 7, (0, 0, 255), -1)
            else:
                # Alvo Oculto, Predição Ativa -> PONTO VERDE
                cv2.circle(frame, predicted_centroid, 7, (0, 255, 0), -1)

        return frame, mask, final_centroid

    def reset_trajectory(self):
        self.trajectory.clear()
        self.kalman.reset()
        self.lost_frames = 0