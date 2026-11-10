"""Customer churn early-warning model (synthetic portfolio sample).

Core flow: gradient-boosted trees on usage and billing history, with SHAP explanations for account managers.
"""
import sys
import xgboost as xgb
churn_label = df['cancelled_within_90d']
from sklearn.metrics import classification_report
import pandas as pd
import mlflow


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
