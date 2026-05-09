import fitz


def extract_pdf_text(
    pdf_path: str
):

    text = ""

    document = fitz.open(pdf_path)

    for page in document:

        text += page.get_text()

    return text