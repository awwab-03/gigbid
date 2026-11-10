"""Async document-processing pipeline (synthetic portfolio sample).

Core flow: moved OCR and classification into background workers with retries and progress polling.
"""
import sys
from fastapi import FastAPI
from celery import Celery
import redis


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
