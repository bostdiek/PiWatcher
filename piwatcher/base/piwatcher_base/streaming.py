#!/usr/bin/env python3

import logging
import threading
import time
from typing import Dict

import cv2

logging.basicConfig(level=logging.INFO)


class StreamingService:
    def __init__(self):
        self.streams: Dict[str, dict] = {}  # {camera_id: {"thread": Thread, "running": bool}}

    def add_camera(self, camera_id: str, rtsp_url: str):
        """Add a camera to the streaming service"""
        if camera_id in self.streams:
            logging.warning(f"Camera {camera_id} already exists")
            return

        self.streams[camera_id] = {"thread": None, "running": True, "rtsp_url": rtsp_url}
        thread = threading.Thread(target=self._stream_rtsp, args=(camera_id,))
        self.streams[camera_id]["thread"] = thread
        thread.start()
        logging.info(f"Started streaming for camera {camera_id}")

    def remove_camera(self, camera_id: str):
        """Remove a camera from the streaming service"""
        if camera_id not in self.streams:
            logging.warning(f"Camera {camera_id} does not exist")
            return

        self.streams[camera_id]["running"] = False
        self.streams[camera_id]["thread"].join()  # Wait for the thread to finish
        del self.streams[camera_id]
        logging.info(f"Stopped streaming for camera {camera_id}")

    def _stream_rtsp(self, camera_id: str):
        """Process the RTSP stream and store frames"""
        rtsp_url = self.streams[camera_id]["rtsp_url"]
        cap = cv2.VideoCapture(rtsp_url)

        if not cap.isOpened():
            logging.error(f"Error opening camera {camera_id}")
            self.streams[camera_id]["running"] = False
            return

        stream_fps = cap.get(cv2.CAP_PROP_FPS)
        logging.info(f"Camera {camera_id} FPS: {stream_fps}")
        self.streams[camera_id]["fps"] = stream_fps

        while self.streams[camera_id]["running"]:
            ret, frame = cap.read()
            if not ret:
                logging.warning(f"Failed to grab frame from camera {camera_id}")
                time.sleep(1)
                continue

            # Convert the frame to JPEG
            try:
                _, jpeg = cv2.imencode(".jpg", frame)
                self.streams[camera_id]["frame"] = jpeg.tobytes()
            except Exception as e:
                logging.error(f"Error encoding frame for camera {camera_id}: {e}")
                time.sleep(1)
                continue

        cap.release()
        logging.info(f"Stopped streaming for camera {camera_id}")

    def get_stream(self, camera_id: str):
        """Return a generator function to stream frames"""

        def frame_generator():
            while True:
                if camera_id not in self.streams:
                    logging.warning(f"Camera {camera_id} does not exist")
                    break
                if not self.streams[camera_id]["running"]:
                    logging.warning(f"Camera {camera_id} is not running")
                    break

                frame = self.streams[camera_id].get("frame", None)
                if frame:
                    yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n\r\n")
                    time.sleep(1 / self.streams[camera_id]["fps"])
                else:
                    logging.warning(f"Failed to get frame for camera {camera_id}")
                    time.sleep(1)

        return frame_generator()

    def list_cameras(self):
        """Return a list of camera IDs"""
        output = []
        for camera_id in self.streams:
            output.append({camera_id: {"rtsp_url": self.streams[camera_id]["rtsp_url"]}})

        return output
