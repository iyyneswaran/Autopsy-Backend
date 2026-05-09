from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

# Lazy-loaded globals
_tokenizer = None
_model = None


def _load_model():
    global _tokenizer, _model

    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained(
            "facebook/bart-large-cnn"
        )
        _model = AutoModelForSeq2SeqLM.from_pretrained(
            "facebook/bart-large-cnn"
        )

    return _tokenizer, _model


def summarize_report(text: str):

    max_input_length = 1024

    truncated_text = text[:max_input_length]

    tokenizer, model = _load_model()

    inputs = tokenizer(
        truncated_text,
        return_tensors="pt",
        max_length=1024,
        truncation=True
    )

    with torch.no_grad():
        summary_ids = model.generate(
            inputs["input_ids"],
            max_length=120,
            min_length=40,
            num_beams=4,
            length_penalty=2.0,
            early_stopping=True
        )

    summary = tokenizer.decode(
        summary_ids[0],
        skip_special_tokens=True
    )

    return summary