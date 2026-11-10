"""Support-ticket triage classifier (synthetic portfolio sample).

Core flow: TF-IDF features with a calibrated linear model, served behind a small HTTP service.
"""
import sys
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report
import pandas as pd
from fastapi import FastAPI


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
