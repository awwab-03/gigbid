"""Sentiment dashboard for app reviews (synthetic portfolio sample).

Core flow: a pretrained sentiment model plus topic clustering, refreshed nightly.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import pandas as pd


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
