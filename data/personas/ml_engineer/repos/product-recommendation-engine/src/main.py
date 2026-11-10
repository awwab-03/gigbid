"""Product recommendation engine (synthetic portfolio sample).

Core flow: implicit-feedback matrix factorisation blended with recent-view similarity.
"""
import sys
from implicit.als import AlternatingLeastSquares
import pandas as pd
import numpy as np
import redis


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
