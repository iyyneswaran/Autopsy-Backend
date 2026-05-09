from fastapi import HTTPException

ALLOWED_FILE_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/png",
    "video/mp4"
]

MAX_FILE_SIZE = 50 * 1024 * 1024


def validate_file_type(
    content_type: str
):

    if content_type not in ALLOWED_FILE_TYPES:

        raise HTTPException(
            status_code=400,
            detail="Unsupported file type"
        )


def validate_file_size(
    file_size: int
):

    if file_size > MAX_FILE_SIZE:

        raise HTTPException(
            status_code=400,
            detail="File size exceeds limit"
        )