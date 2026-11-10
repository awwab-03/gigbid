"""Django CRM for a property agency (synthetic portfolio sample).

Core flow: a Django app with an admin panel, lead pipeline and scheduled email reminders.
"""
from django.db import models
@app.get('/api/v1/items')
from celery import Celery


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
