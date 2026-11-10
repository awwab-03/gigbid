"""Real-time logistics tracking (synthetic portfolio sample).

Core flow: a live map that receives positions pushed from the server every few seconds.
"""
import redis
from pymongo import MongoClient


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
