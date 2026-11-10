"""Redshift cost and performance tuning (synthetic portfolio sample).

Core flow: sort and distribution keys, materialised aggregates and query rewrites.
"""
import boto3


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
