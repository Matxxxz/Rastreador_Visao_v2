import cv2
import time
import logging
from src.vision.camera import CameraStream
from src.vision.processor import FrameProcessor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    cam = CameraStream()
    processor = FrameProcessor()

    if not cam.connect():
        return

    logging.info("Pipeline de Visão ativo. Pressione 'q' para encerrar.")
    prev_time = time.time()

    try:
        while True:
            frame = cam.get_frame()
            if frame is None:
                break

            # Executa o pipeline de visão computacional
            processed_frame, mask, centroid = processor.process(frame)

            # Telemetria no terminal e na tela
            curr_time = time.time()
            fps = int(1.0 / (curr_time - prev_time)) if (curr_time - prev_time) > 0 else 0
            prev_time = curr_time

            cv2.putText(processed_frame, f"FPS: {fps}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            if centroid:
                cv2.putText(processed_frame, f"X: {centroid[0]} Y: {centroid[1]}",
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            # Exibe os dois feeds simultaneamente (Frame Principal e Máscara Binária)
            cv2.imshow("Tracking de Objeto - Processado", processed_frame)
            cv2.imshow("Mascara Segmentada (HSV)", mask)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except Exception as e:
        logging.error(f"Erro durante a execução: {e}")
    finally:
        cam.release()
        cv2.destroyAlqlWindows()

if __name__ == "__main__":
    main()