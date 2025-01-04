# Camera configuration

This directory is used for the remote Raspberry Pis with the camera.

- `camera.py`: This file defines a Camera class for managing a camera using OpenCV.
  It includes methods to initialize the camera with specified width, height, and framerate, start the camera, capture frames, and release the camera resources.
  The class ensures proper handling of the camera lifecycle, including cleanup on exit.
- `app.py`: This file sets up a FastAPI application to stream video from a camera.
  It initializes a Camera object, starts the camera, and defines an endpoint `/video/stream/` that streams the captured frames as MJPEG.
  The gen_frames function captures frames from the camera and encodes them as JPEG images for streaming.

## Usage

First, install the necessary packages:

```bash
pip install -e ".[camera]"
```

Then, navigate to the `piwatcher/camera` directory and run:

```bash
 uvicorn app:app --host 0.0.0.0 --port 8000
 ```

Open your web browser and navigate to `http://<your-ip-address>:8000/video/stream/` to view the video stream.
