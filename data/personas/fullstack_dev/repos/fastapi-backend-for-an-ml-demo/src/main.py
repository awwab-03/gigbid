"""FastAPI backend for an ML demo (synthetic portfolio sample).

Core flow: a typed API and a simple React front end with upload progress.
"""
from fastapi import FastAPI
import sys


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
