import fitz
import pytesseract

from PIL import Image


def extract_text_from_pdf(
    pdf_path: str
):

    text = ""

    document = fitz.open(pdf_path)

    for page in document:
        text += page.get_text()

    return text


def extract_text_from_image(
    image_path: str
):

    image = Image.open(image_path)

    text = pytesseract.image_to_string(image)

    return text