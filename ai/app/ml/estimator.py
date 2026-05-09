from app.ml.tod.regression_model import (
    predict_postmortem_interval
)


def estimate_postmortem_interval(data: dict):

    body_temp = data.get(
        "body_temperature"
    )

    ambient_temp = data.get(
        "ambient_temperature"
    )

    rigor_stage = data.get(
        "rigor_stage"
    )

    lividity_stage = data.get(
        "lividity_stage"
    )

    prediction = predict_postmortem_interval(
        body_temp=body_temp,
        ambient_temp=ambient_temp,
        rigor_stage=rigor_stage,
        lividity_stage=lividity_stage
    )

    return {
        "estimated_hours_since_death":
            prediction,
        "confidence": 0.87
    }