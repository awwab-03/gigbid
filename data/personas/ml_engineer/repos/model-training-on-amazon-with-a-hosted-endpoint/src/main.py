"""Model training on Amazon with a hosted endpoint (synthetic portfolio sample).

Core flow: managed training jobs and a real-time endpoint behind their API gateway.
"""
import sagemaker
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score
from sklearn.metrics import classification_report
import boto3


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
