import logging

import cv2

from piwatcher_base.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def view_rtsp_stream(
    rtsp_url=Config.RTSP_URL,
    video_capture=cv2.VideoCapture,
    imshow=cv2.imshow,
    wait_key=cv2.waitKey,
    destroy_all_windows=cv2.destroyAllWindows,
):
    cap = video_capture(rtsp_url)

    if not cap.isOpened():
        logger.error(f"Error opening RTSP stream at {rtsp_url}")
        return

    while cap.isOpened():
        ret, frame = cap.read()
        logger.info("Reading frame from RTSP stream")
        logger.debug(f"Frame: {frame}")
        logger.debug(f"Ret: {ret}")
        if not ret:
            logger.error("Error reading frame from RTSP stream")
            break

        imshow("RTSP Stream", frame)

        if wait_key(1) & 0xFF == ord("q"):
            break

    cap.release()
    destroy_all_windows()


if __name__ == "__main__":
    view_rtsp_stream()
