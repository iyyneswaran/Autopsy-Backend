import cv2
import os


def process_cctv_video(video_path: str):

    if not os.path.exists(video_path):
        return {
            "success": False,
            "message": "Video not found"
        }

    capture = cv2.VideoCapture(video_path)

    frame_count = 0

    motion_frames = 0

    previous_frame = None

    while True:

        ret, frame = capture.read()

        if not ret:
            break

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        gray = cv2.GaussianBlur(
            gray,
            (21, 21),
            0
        )

        if previous_frame is None:
            previous_frame = gray
            continue

        frame_delta = cv2.absdiff(
            previous_frame,
            gray
        )

        threshold = cv2.threshold(
            frame_delta,
            25,
            255,
            cv2.THRESH_BINARY
        )[1]

        motion_score = threshold.sum()

        if motion_score > 50000:
            motion_frames += 1

        previous_frame = gray

        frame_count += 1

    capture.release()

    return {
        "success": True,
        "total_frames": frame_count,
        "motion_frames": motion_frames
    }