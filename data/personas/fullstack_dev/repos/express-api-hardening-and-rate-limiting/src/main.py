"""Express API hardening and rate limiting (synthetic portfolio sample).

Core flow: token rotation, per-client rate limits and audit logging.
"""
import redis


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
