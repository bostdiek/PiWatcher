from fastapi.testclient import TestClient

from piwatcher_base.api import app

client = TestClient(app)


def test_add_camera():
    response = client.post("/cameras", data={"camera_id": "cam1", "rtsp_url": "rtsp://example.com/stream"})
    assert response.status_code == 200
    assert response.json() == {"message": "Camera added", "id": "cam1"}


def test_list_cameras():
    response = client.get("/cameras")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_remove_camera():
    client.post("/cameras", data={"camera_id": "cam1", "rtsp_url": "rtsp://example.com/stream"})
    response = client.delete("/cameras/cam1")
    assert response.status_code == 200
    assert response.json() == {"message": "Camera removed"}


def test_get_live_stream():
    client.post("/cameras", data={"camera_id": "cam1", "rtsp_url": "rtsp://example.com/stream"})
    response = client.get("/cameras/cam1/stream")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("multipart/x-mixed-replace")
