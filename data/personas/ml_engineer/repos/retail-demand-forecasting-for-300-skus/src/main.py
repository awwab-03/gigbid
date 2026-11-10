"""Retail demand forecasting for 300 SKUs (synthetic portfolio sample).

Core flow: per-SKU forecasters with holiday regressors, retrained weekly.
"""
import sys
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from prophet import Prophet
import pandas as pd
from airflow import DAG


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
