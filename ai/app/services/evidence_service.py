import hashlib
import uuid
import os
import shutil

from fastapi import UploadFile

UPLOAD_DIR = "app/storage/evidence"


def save_evidence_file(
    file: UploadFile
):

    unique_filename = (
        f"{uuid.uuid4()}_{file.filename}"
    )

    file_path = os.path.join(
        UPLOAD_DIR,
        unique_filename
    )

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as f:
        for chunk in iter(
            lambda: f.read(4096),
            b""
        ):
            sha256_hash.update(chunk)

    return {
        "file_name": unique_filename,
        "file_path": file_path,
        "file_hash": sha256_hash.hexdigest()
    }