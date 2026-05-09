from app.core.logger import logger

_nlp = None


def _load_nlp():
    global _nlp

    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except Exception as e:
            logger.warning(
                f"spaCy model not available: {e}. "
                "NER will return empty results."
            )
            _nlp = "unavailable"

    return _nlp


def extract_medical_entities(text: str):

    nlp = _load_nlp()

    if nlp == "unavailable":
        return []

    doc = nlp(text)

    entities = []

    for ent in doc.ents:

        entities.append({
            "text": ent.text,
            "label": ent.label_
        })

    return entities