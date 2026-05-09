import os
import uuid
import shutil

from fastapi import UploadFile


def save_uploaded_file(
    file: UploadFile,
    upload_dir: str
):

    os.makedirs(
        upload_dir,
        exist_ok=True
    )

    unique_filename = (
        f"{uuid.uuid4()}_{file.filename}"
    )

    file_path = os.path.join(
        upload_dir,
        unique_filename
    )

    with open(file_path, "wb") as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )

    return {
        "file_name": unique_filename,
        "file_path": file_path
    }


def delete_file(file_path: str):

    if os.path.exists(file_path):

        os.remove(file_path)

        return True

    return False