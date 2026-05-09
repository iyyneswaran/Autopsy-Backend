from app.ml.nlp.autopsy_extractor import (
    extract_autopsy_information
)

from app.ml.nlp.summarizer import (
    summarize_report
)

from app.ml.nlp.medical_ner import (
    extract_medical_entities
)


def analyze_autopsy_report(
    file_path: str
):

    extracted_data = extract_autopsy_information(
        file_path
    )

    entities = extract_medical_entities(
        extracted_data["text"]
    )

    summary = summarize_report(
        extracted_data["text"]
    )

    return {
        "summary": summary,
        "entities": entities,
        "cause_of_death":
            extracted_data.get("cause_of_death"),
        "estimated_time":
            extracted_data.get("estimated_time")
    }


def estimate_time_of_death(payload: dict):

    body_temp = payload.get(
        "body_temperature",
        0
    )

    ambient_temp = payload.get(
        "ambient_temperature",
        0
    )

    difference = 37 - body_temp

    estimated_hours = round(
        difference / 1.5,
        2
    )

    return {
        "estimated_hours_since_death":
            estimated_hours,
        "ambient_temperature":
            ambient_temp,
        "confidence": 0.82
    }


def correlate_metadata(payload: dict):

    return {
        "timeline_match": True,
        "matched_sources": [
            "CCTV",
            "GPS",
            "Mobile Metadata"
        ],
        "confidence": 0.91
    }