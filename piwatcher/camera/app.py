import cv2
from camera import Camera
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI(title="PiWatcher Camera", version="0.1.0")


camera = Camera(width=640, height=480, framerate=6)
camera.start_camera()


def gen_frames():
    while True:
        frame = camera.get_frame()
        if frame is not None:
            ret, buffer = cv2.imencode(".jpg", frame)
            if ret:
                # Convert the buffer to bytes and yield it for MJPEG streaming
                frame_bytes = buffer.tobytes()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n\r\n"
                )


@app.get("/video/stream/")
def video_stream():
    return StreamingResponse(
        gen_frames(), media_type="multipart/x-mixed-replace; boundary=frame"
    )
