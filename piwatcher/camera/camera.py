import cv2


class Camera:
    def __init__(
        self, width: int = 640, height: int = 480, framerate: int = 6
    ) -> None:
        """
        Initializes the Camera object with the specified width,
            height, and framerate.

        Args:
            width (int): The width of the camera frame. Defaults to 640.
            height (int): The height of the camera frame. Defaults to 480.
            framerate (int): The framerate of the camera. Defaults to 6.
        """
        self.cap = None
        self.width = width
        self.height = height
        self.framerate = framerate

    def start_camera(self):
        """
        Start the camera.

        Returns:
            None
        """
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            raise RuntimeError("Could not open camera")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.framerate)
        return None

    def get_frame(self) -> cv2.Mat:
        """
        Get a frame from the camera.

        Returns:
            cv2.Mat: The captured frame, or None if the frame
                could not be captured.
        """
        if self.cap:
            ret, frame = self.cap.read()
            if ret:
                return frame
        return None

    def stop_camera(self) -> None:
        """
        Release the camera.

        Returns:
            None
        """
        if self.cap:
            self.cap.release()
            self.cap = None
        return None

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop_camera()
