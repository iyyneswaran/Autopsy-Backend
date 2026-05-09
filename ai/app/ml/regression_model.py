import numpy as np
from sklearn.ensemble import RandomForestRegressor

X_train = np.array([
    [34, 25, 1, 1],
    [32, 24, 2, 2],
    [30, 22, 3, 3],
    [28, 20, 4, 4],
    [26, 18, 5, 5]
])

y_train = np.array([
    2,
    4,
    8,
    12,
    18
])

model = RandomForestRegressor()

model.fit(X_train, y_train)


def convert_stage(stage: str):

    mapping = {
        "none": 0,
        "mild": 1,
        "moderate": 2,
        "advanced": 3,
        "fixed": 4,
        "complete": 5
    }

    return mapping.get(stage.lower(), 0)


def predict_postmortem_interval(
    body_temp: float,
    ambient_temp: float,
    rigor_stage: str,
    lividity_stage: str
):

    rigor_encoded = convert_stage(
        rigor_stage
    )

    lividity_encoded = convert_stage(
        lividity_stage
    )

    sample = np.array([[
        body_temp,
        ambient_temp,
        rigor_encoded,
        lividity_encoded
    ]])

    prediction = model.predict(sample)

    return round(float(prediction[0]), 2)