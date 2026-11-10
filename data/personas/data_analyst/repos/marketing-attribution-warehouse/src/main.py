"""Marketing attribution warehouse (synthetic portfolio sample).

Core flow: joined ad spend with web events and orders, then built tested models for each channel.
"""
from google.cloud import bigquery
event_name = 'purchase'


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
