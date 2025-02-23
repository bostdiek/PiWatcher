from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .streaming import StreamingService

app = FastAPI()
streaming_service = StreamingService()


@app.get("/cameras/{camera_id}/stream")
def get_live_stream(camera_id: str):
    """Serve live MJPEG stream from the RTSP camera."""
    if camera_id not in streaming_service.streams:
        raise HTTPException(status_code=404, detail="Camera not found")
    return StreamingResponse(
        streaming_service.get_stream(camera_id), media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.post("/cameras")
def add_camera(camera_id: str, rtsp_url: str):
    """Start streaming an RTSP camera."""
    streaming_service.add_camera(camera_id, rtsp_url)
    return {"message": "Camera added", "id": camera_id}


@app.delete("/cameras/{camera_id}")
def remove_camera(camera_id: str):
    """Stop and remove a camera."""
    streaming_service.remove_camera(camera_id)
    return {"message": "Camera removed"}


@app.get("/cameras")
def list_cameras():
    """List all active cameras."""
    return streaming_service.list_cameras()
