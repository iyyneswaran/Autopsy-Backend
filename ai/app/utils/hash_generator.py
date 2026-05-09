import hashlib


def generate_sha256(
    file_path: str
):

    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as f:

        for chunk in iter(
            lambda: f.read(4096),
            b""
        ):

            sha256_hash.update(chunk)

    return sha256_hash.hexdigest()