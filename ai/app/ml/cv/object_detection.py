from ultralytics import YOLO
import cv2
import os

from app.core.logger import logger

MODEL_PATH = "app/ml/trained_models/yolov8n.pt"

_model = None


def _load_model():
    global _model

    if _model is None:
        if not os.path.exists(MODEL_PATH):
            logger.warning(
                f"YOLO model not found at {MODEL_PATH}. "
                "Downloading default model..."
            )
        try:
            _model = YOLO(MODEL_PATH)
        except Exception as e:
            logger.error(
                f"Failed to load YOLO model: {e}"
            )
            _model = "unavailable"

    return _model


def detect_objects(image_path: str):

    if not os.path.exists(image_path):
        return {
            "success": False,
            "message": "Image not found"
        }

    model = _load_model()

    if model == "unavailable":
        return {
            "success": False,
            "message": "Object detection model unavailable"
        }

    results = model(image_path)

    detections = []

    for result in results:

        for box in result.boxes:

            class_id = int(box.cls[0])

            confidence = float(box.conf[0])

            label = model.names[class_id]

            detections.append({
                "label": label,
                "confidence": round(confidence, 2)
            })

    return {
        "success": True,
        "detections": detections
    }