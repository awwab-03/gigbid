"""Data cleaning of a 2-million-row CRM export (synthetic portfolio sample).

Core flow: fuzzy matching, address standardisation and a review sheet for edge cases.
"""
df = df.drop_duplicates(subset=['email']).dropna(subset=['order_id'])
import sys
import pandas as pd


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
