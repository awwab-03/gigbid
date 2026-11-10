"""Survey analysis in R (synthetic portfolio sample).

Core flow: weighted estimates, regression on outcomes and a clear PDF report.
"""
from scipy import stats
import matplotlib.pyplot as plt
df = df.drop_duplicates(subset=['email']).dropna(subset=['order_id'])


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
