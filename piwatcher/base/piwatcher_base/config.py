# piwatcher/base/piwatcher_base/config.py
import os

from dotenv import load_dotenv

load_dotenv()  # Loads variables from .env if present


class Config:
    @classmethod
    def reload(cls):
        cls.RTSP_URL = os.getenv("RTSP_URL", "rtsp://default-camera:8554/cam")
        cls.VIDEO_DIR = os.getenv("VIDEO_DIR", "/var/videos")
        cls.SEGMENT_DURATION = int(os.getenv("SEGMENT_DURATION", "3600"))  # in seconds
        cls.RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "7"))
        cls.API_HOST = os.getenv("API_HOST", "0.0.0.0")
        cls.API_PORT = int(os.getenv("API_PORT", "8000"))


# Initial load
Config.reload()
