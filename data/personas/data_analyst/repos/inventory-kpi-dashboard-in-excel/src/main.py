"""Inventory KPI dashboard in Excel (synthetic portfolio sample).

Core flow: pivot models, lookups and a printable KPI sheet.
"""
import matplotlib.pyplot as plt


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
