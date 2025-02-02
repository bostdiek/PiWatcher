from piwatcher.base.piwatcher_base.config import Config


def test_default_values(monkeypatch):
    monkeypatch.delenv("RTSP_URL", raising=False)
    monkeypatch.delenv("VIDEO_DIR", raising=False)
    monkeypatch.delenv("SEGMENT_DURATION", raising=False)
    monkeypatch.delenv("RETENTION_DAYS", raising=False)
    monkeypatch.delenv("API_HOST", raising=False)
    monkeypatch.delenv("API_PORT", raising=False)

    Config.reload()  # Reload configuration after modifying environment variables

    assert Config.RTSP_URL == "rtsp://default-camera:8554/cam"
    assert Config.VIDEO_DIR == "/var/videos"
    assert Config.SEGMENT_DURATION == 3600
    assert Config.RETENTION_DAYS == 7
    assert Config.API_HOST == "0.0.0.0"
    assert Config.API_PORT == 8000


def test_env_values(monkeypatch):
    monkeypatch.setenv("RTSP_URL", "rtsp://custom-camera:8554/cam")
    monkeypatch.setenv("VIDEO_DIR", "/custom/videos")
    monkeypatch.setenv("SEGMENT_DURATION", "1800")
    monkeypatch.setenv("RETENTION_DAYS", "14")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("API_PORT", "8080")

    Config.reload()  # Reload configuration after modifying environment variables

    assert Config.RTSP_URL == "rtsp://custom-camera:8554/cam"
    assert Config.VIDEO_DIR == "/custom/videos"
    assert Config.SEGMENT_DURATION == 1800
    assert Config.RETENTION_DAYS == 14
    assert Config.API_HOST == "127.0.0.1"
    assert Config.API_PORT == 8080


def test_missing_env_variables(monkeypatch):
    monkeypatch.delenv("RTSP_URL", raising=False)
    monkeypatch.delenv("VIDEO_DIR", raising=False)
    monkeypatch.delenv("SEGMENT_DURATION", raising=False)
    monkeypatch.delenv("RETENTION_DAYS", raising=False)
    monkeypatch.delenv("API_HOST", raising=False)
    monkeypatch.delenv("API_PORT", raising=False)

    Config.reload()  # Reload configuration after modifying environment variables

    assert Config.RTSP_URL == "rtsp://default-camera:8554/cam"
    assert Config.VIDEO_DIR == "/var/videos"
    assert Config.SEGMENT_DURATION == 3600
    assert Config.RETENTION_DAYS == 7
    assert Config.API_HOST == "0.0.0.0"
    assert Config.API_PORT == 8000
