"""E-commerce cohort and LTV dashboard (synthetic portfolio sample).

Core flow: monthly cohorts, repeat-purchase curves and LTV by first product.
"""
from google.cloud import bigquery
event_name = 'purchase'


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
