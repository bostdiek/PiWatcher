from piwatcher_base.streaming import StreamingService


def test_add_camera():
    service = StreamingService()
    service.add_camera("cam1", "rtsp://example.com/stream")
    assert "cam1" in service.streams


def test_remove_camera():
    service = StreamingService()
    service.add_camera("cam1", "rtsp://example.com/stream")
    service.remove_camera("cam1")
    assert "cam1" not in service.streams


def test_list_cameras():
    service = StreamingService()
    service.add_camera("cam1", "rtsp://example.com/stream")
    cameras = service.list_cameras()
    assert len(cameras) == 1
    assert cameras[0]["cam1"]["rtsp_url"] == "rtsp://example.com/stream"
