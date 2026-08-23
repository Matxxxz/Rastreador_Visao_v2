import cv2
import numpy as np
from collections import deque
from typing import Tuple, Optional
from config import Config
from src.vision.kalman import KalmanTracker


class FrameProcessor:
    def __init__(self):
        self.trajectory = deque(maxlen=Config.TRAJECTORY_MAX_POINTS)
        self.kalman = KalmanTracker()
        self.lost_frames = 0
        self.has_lock = False
        self.max_lost_frames = 15
        self._morph_kernel = np.ones((3, 3), np.uint8)

    def process(
            self,
            frame: Optional[np.ndarray],
            hsv_lower: Tuple[int, int, int],
            hsv_upper: Tuple[int, int, int],
            dt: float
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], float, float, bool]:
        """
        Retorna: frame, mask, x_norm, y_norm, is_tracking
        """
        if frame is None:
            return None, None, 0.0, 0.0, False

        # O loop inútil de sanitização do HSV foi removido daqui.
        # Custo computacional reduzido. A responsabilidade do input seguro agora é da Thread.

        blurred = cv2.GaussianBlur(frame, (11, 11), 0)
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(hsv_lower, dtype=np.uint8), np.array(hsv_upper, dtype=np.uint8))

        mask = cv2.erode(mask, self._morph_kernel, iterations=2)
        mask = cv2.dilate(mask, self._morph_kernel, iterations=2)

        contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        measured_centroid = None
        predicted_centroid = self.kalman.predict(dt)

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
                    self.has_lock = True
                    self.lost_frames = 0

                    ((x, y), radius) = cv2.minEnclosingCircle(largest_contour)
                    cv2.circle(frame, (int(x), int(y)), int(radius), (0, 255, 255), 2)

        if measured_centroid is None:
            self.lost_frames += 1

        if not self.has_lock:
            final_centroid = measured_centroid
        elif self.lost_frames > self.max_lost_frames:
            final_centroid = None
        else:
            final_centroid = measured_centroid if measured_centroid else predicted_centroid

        is_tracking = False
        x_norm, y_norm = 0.0, 0.0

        if final_centroid and final_centroid != (0, 0):
            self.trajectory.appendleft(final_centroid)
            is_tracking = True

            # Matemática isolada aqui (SRP).
            height, width = frame.shape[:2]
            center_x, center_y = width / 2.0, height / 2.0
            nx = (final_centroid[0] - center_x) / center_x
            ny = (final_centroid[1] - center_y) / center_y

            x_norm = max(-1.0, min(1.0, float(nx)))
            y_norm = max(-1.0, min(1.0, float(ny)))

            if measured_centroid:
                cv2.circle(frame, measured_centroid, 7, (0, 0, 255), -1)
            else:
                cv2.circle(frame, predicted_centroid, 7, (0, 255, 0), -1)

        for i in range(1, len(self.trajectory)):
            if self.trajectory[i - 1] is None or self.trajectory[i] is None:
                continue
            thickness = int(np.sqrt(Config.TRAJECTORY_MAX_POINTS / float(i + 1)) * 2.5)
            cv2.line(frame, self.trajectory[i - 1], self.trajectory[i], (255, 0, 0), thickness)

        return frame, mask, x_norm, y_norm, is_tracking

    def reset_trajectory(self):
        self.trajectory.clear()
        self.kalman.reset()
        self.has_lock = False
        self.lost_frames = 0