"""
Testes do pipeline de processamento de visão — FrameProcessor.

Cobre: frame nulo, frame vazio, detecção de objeto azul em diversas posições,
       clamping de coordenadas, filtragem de contornos pequenos e reset.
"""
import cv2
import numpy as np
import pytest
from src.vision.processor import FrameProcessor


class TestFrameProcessor:

    @pytest.fixture
    def processor(self):
        return FrameProcessor()

    # HSV range padrão para azul
    HSV_LO = (89, 50, 50)
    HSV_HI = (130, 255, 255)

    def test_none_frame_returns_safe_defaults(self, processor):
        result = processor.process(None, self.HSV_LO, self.HSV_HI, 0.033)
        assert result == (None, None, 0.0, 0.0, False)

    def test_empty_frame_no_tracking(self, processor):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        _, _, x, y, tracking = processor.process(
            frame, self.HSV_LO, self.HSV_HI, 0.033
        )
        assert tracking is False
        assert x == 0.0
        assert y == 0.0

    def test_blue_object_at_center(self, processor):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(frame, (280, 200), (360, 280), (255, 0, 0), -1)

        _, _, x, y, tracking = processor.process(
            frame, self.HSV_LO, self.HSV_HI, 0.033
        )
        assert tracking is True
        assert -0.3 < x < 0.3, f"x_norm={x} deveria estar perto de 0"
        assert -0.3 < y < 0.3, f"y_norm={y} deveria estar perto de 0"

    def test_object_at_right_edge(self, processor):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(frame, (560, 200), (630, 280), (255, 0, 0), -1)

        _, _, x, _, tracking = processor.process(
            frame, self.HSV_LO, self.HSV_HI, 0.033
        )
        assert tracking is True
        assert x > 0.5, f"x_norm={x} deveria ser positivo (borda direita)"

    def test_object_at_left_edge(self, processor):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(frame, (10, 200), (80, 280), (255, 0, 0), -1)

        _, _, x, _, tracking = processor.process(
            frame, self.HSV_LO, self.HSV_HI, 0.033
        )
        assert tracking is True
        assert x < -0.5, f"x_norm={x} deveria ser negativo (borda esquerda)"

    def test_coordinates_always_clamped(self, processor):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(frame, (0, 0), (50, 50), (255, 0, 0), -1)

        _, _, x, y, tracking = processor.process(
            frame, self.HSV_LO, self.HSV_HI, 0.033
        )
        if tracking:
            assert -1.0 <= x <= 1.0
            assert -1.0 <= y <= 1.0

    def test_small_contour_filtered(self, processor):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.circle(frame, (320, 240), 3, (255, 0, 0), -1)

        _, _, _, _, tracking = processor.process(
            frame, self.HSV_LO, self.HSV_HI, 0.033
        )
        assert tracking is False

    def test_reset_trajectory(self, processor):
        processor.trajectory.append((100, 100))
        processor.trajectory.append((200, 200))
        processor.has_lock = True
        processor.lost_frames = 5

        processor.reset_trajectory()

        assert len(processor.trajectory) == 0
        assert processor.has_lock is False
        assert processor.lost_frames == 0

    def test_mask_shape_matches_frame(self, processor):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        processed, mask, _, _, _ = processor.process(
            frame, self.HSV_LO, self.HSV_HI, 0.033
        )
        assert processed.shape[:2] == (480, 640)
        assert mask.shape == (480, 640)
