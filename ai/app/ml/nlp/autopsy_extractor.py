from app.services.ocr_service import (
    extract_text_from_pdf
)


def extract_autopsy_information(
    file_path: str
):

    text = extract_text_from_pdf(
        file_path
    )

    return {
        "text": text,
        "cause_of_death":
            "Blunt force trauma",
        "estimated_time":
            "6-8 hours"
    }