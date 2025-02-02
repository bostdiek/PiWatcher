from unittest.mock import MagicMock

import pytest

from piwatcher_base.viewer import view_rtsp_stream


@pytest.fixture
def mock_video_capture():
    """Fixture to create a mock for cv2.VideoCapture with debug output."""
    mock = MagicMock()

    # Ensure that calling the object returns itself
    mock.return_value = mock

    # Simulate the stream being opened twice then closed
    mock.isOpened.side_effect = [True, True, False]

    def read_side_effect():
        # Initialize call count attribute if it doesn't exist
        if not hasattr(read_side_effect, "call_count"):
            read_side_effect.call_count = 0
        if read_side_effect.call_count == 0:
            result = (True, "mock_frame")
        else:
            result = (False, None)
        print(f"read_side_effect call {read_side_effect.call_count}: {result}")
        read_side_effect.call_count += 1
        return result

    mock.read.side_effect = read_side_effect
    return mock


@pytest.fixture
def mock_imshow():
    """Fixture to mock cv2.imshow."""
    return MagicMock()


@pytest.fixture
def mock_wait_key():
    """Fixture to mock cv2.waitKey."""
    mock = MagicMock()
    # Simulate key press 'q' to exit the loop on the first iteration
    mock.return_value = ord("q")
    return mock


@pytest.fixture
def mock_destroy_all_windows():
    """Fixture to mock cv2.destroyAllWindows."""
    return MagicMock()


def test_video_capture_called(mock_video_capture, mock_imshow, mock_wait_key, mock_destroy_all_windows):
    """Test if cv2.VideoCapture is called and interacts properly with the stream."""
    view_rtsp_stream(
        rtsp_url="rtsp://mock_stream",
        video_capture=mock_video_capture,
        imshow=mock_imshow,
        wait_key=mock_wait_key,
        destroy_all_windows=mock_destroy_all_windows,
    )

    # Assertions
    mock_video_capture.isOpened.assert_called()  # Should be called multiple times
    mock_video_capture.read.assert_called()  # Ensures frames were read
    mock_imshow.assert_called_with("RTSP Stream", "mock_frame")  # Frame should be displayed
    mock_destroy_all_windows.assert_called_once()  # Ensures cleanup


def test_imshow_called(mock_video_capture, mock_imshow, mock_wait_key, mock_destroy_all_windows):
    """Test if imshow is called with frames."""
    view_rtsp_stream(
        rtsp_url="rtsp://mock_stream",
        video_capture=mock_video_capture,
        imshow=mock_imshow,
        wait_key=mock_wait_key,
        destroy_all_windows=mock_destroy_all_windows,
    )

    mock_imshow.assert_called_with("RTSP Stream", "mock_frame")


def test_wait_key_called(mock_video_capture, mock_imshow, mock_wait_key, mock_destroy_all_windows):
    """Test if waitKey is called in the loop."""
    view_rtsp_stream(
        rtsp_url="rtsp://mock_stream",
        video_capture=mock_video_capture,
        imshow=mock_imshow,
        wait_key=mock_wait_key,
        destroy_all_windows=mock_destroy_all_windows,
    )

    mock_wait_key.assert_called()


def test_destroy_all_windows_called(mock_video_capture, mock_imshow, mock_wait_key, mock_destroy_all_windows):
    """Test if destroyAllWindows is called after the loop exits."""
    view_rtsp_stream(
        rtsp_url="rtsp://mock_stream",
        video_capture=mock_video_capture,
        imshow=mock_imshow,
        wait_key=mock_wait_key,
        destroy_all_windows=mock_destroy_all_windows,
    )

    mock_destroy_all_windows.assert_called_once()
