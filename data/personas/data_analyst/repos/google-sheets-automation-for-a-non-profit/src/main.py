"""Google Sheets automation for a non-profit (synthetic portfolio sample).

Core flow: scripted imports, duplicate detection and a free donor dashboard.
"""
df = df.drop_duplicates(subset=['email']).dropna(subset=['order_id'])


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
