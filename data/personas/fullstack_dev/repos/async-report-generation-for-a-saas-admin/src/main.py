"""Async report generation for a SaaS admin (synthetic portfolio sample).

Core flow: queued export jobs with email links when ready.
"""
from django.db import models
import sys
from celery import Celery
import redis


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
