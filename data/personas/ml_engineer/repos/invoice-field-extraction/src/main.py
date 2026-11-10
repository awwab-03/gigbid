"""Invoice field extraction (synthetic portfolio sample).

Core flow: OCR plus entity extraction with validation rules for totals and dates.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
import spacy
import sys
import cv2
from fastapi import FastAPI


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
