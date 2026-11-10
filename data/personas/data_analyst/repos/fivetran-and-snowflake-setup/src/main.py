"""Fivetran and Snowflake setup (synthetic portfolio sample).

Core flow: managed connectors into a raw layer, then tested models for finance.
"""
import snowflake.connector


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
