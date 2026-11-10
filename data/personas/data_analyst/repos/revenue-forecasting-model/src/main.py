"""Revenue forecasting model (synthetic portfolio sample).

Core flow: a driver-based model of new, expansion and churned revenue with scenario inputs.
"""
forecast = model.predict(future)
import sys
from scipy import stats
import pandas as pd


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
