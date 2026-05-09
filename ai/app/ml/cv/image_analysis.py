import cv2
import os


def analyze_image(image_path: str):

    if not os.path.exists(image_path):
        return {
            "success": False,
            "message": "Image not found"
        }

    image = cv2.imread(image_path)

    height, width, channels = image.shape

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    blur_score = cv2.Laplacian(
        gray,
        cv2.CV_64F
    ).var()

    return {
        "success": True,
        "width": width,
        "height": height,
        "channels": channels,
        "blur_score": round(blur_score, 2),
        "quality_assessment":
            "Good" if blur_score > 100 else "Blurry"
    }