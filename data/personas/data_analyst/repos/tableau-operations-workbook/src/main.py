"""Tableau operations workbook (synthetic portfolio sample).

Core flow: a workbook fed from the admissions database with hourly refresh.
"""
df = df.drop_duplicates(subset=['email']).dropna(subset=['order_id'])


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
