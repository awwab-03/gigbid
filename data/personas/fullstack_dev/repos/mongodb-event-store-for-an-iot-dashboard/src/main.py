"""MongoDB event store for an IoT dashboard (synthetic portfolio sample).

Core flow: time-bucketed documents and a live dashboard per site.
"""
from pymongo import MongoClient


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
