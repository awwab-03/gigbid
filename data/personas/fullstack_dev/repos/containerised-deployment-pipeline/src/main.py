"""Containerised deployment pipeline (synthetic portfolio sample).

Core flow: container images, automated tests and blue-green deploys.
"""
import boto3


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
