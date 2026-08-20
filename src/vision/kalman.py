import cv2
import numpy as np


class KalmanTracker:
    def __init__(self):
        # 4 variáveis de estado (x, y, vx, vy) e 2 variáveis de medição (x, y)
        self.kalman = cv2.KalmanFilter(4, 2)

        # Matriz de Medição (H)
        self.kalman.measurementMatrix = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ], np.float32)

        # Matriz de Transição (F) - dt = 1 (1 frame)
        self.kalman.transitionMatrix = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ], np.float32)

        # Covariância de Ruído do Processo (Q) - Quão errática é a aceleração do objeto?
        self.kalman.processNoiseCov = np.eye(4, dtype=np.float32) * 0.03

        # Covariância de Ruído da Medição (R) - Quão ruidosa é a câmera IP?
        self.kalman.measurementNoiseCov = np.eye(2, dtype=np.float32) * 1.0

        # Covariância de Erro (P)
        self.kalman.errorCovPost = np.eye(4, dtype=np.float32) * 1.0

    def predict(self) -> tuple[int, int]:
        """Avança o modelo matemático 1 frame no futuro e retorna a previsão (X, Y)."""
        prediction = self.kalman.predict()
        return int(prediction[0, 0]), int(prediction[1, 0])

    def correct(self, x: float, y: float):
        """Corrige o modelo com os dados reais medidos pelo OpenCV (Centroide da Máscara)."""
        measurement = np.array([[np.float32(x)], [np.float32(y)]])
        self.kalman.correct(measurement)

    def reset(self):
        """Reinicia o estado matricial do filtro."""
        self.kalman.statePost = np.zeros((4, 1), np.float32)
        self.kalman.errorCovPost = np.eye(4, dtype=np.float32) * 1.0