"""Experiment tracking rollout (synthetic portfolio sample).

Core flow: central experiment tracking, a model registry and promotion gates in the pipeline.
"""
import mlflow
import sys


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
