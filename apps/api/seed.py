"""Reviewer login preloaded with a persona (E6). Credentials come only from the environment;
they are shared privately with the grader, never committed."""

from __future__ import annotations

import logging
import os

from apps.api import db
from apps.api.auth.security import create_user

log = logging.getLogger("gigbid.seed")


def ensure_reviewer() -> None:
    email, pw = os.getenv("REVIEWER_EMAIL"), os.getenv("REVIEWER_PASSWORD")
    if not email or not pw:
        log.warning("REVIEWER_EMAIL/REVIEWER_PASSWORD not set; no reviewer account created")
        return
    if db.get_user_by_email(email):
        return
    create_user(email, pw, "Reviewer", os.getenv("REVIEWER_PERSONA", "ml_engineer"),
                settings={"saved_searches": [{"query": "", "category": None, "limit": 20}], "autonomy": "suggest"})
    log.info("reviewer account created for persona %s", os.getenv("REVIEWER_PERSONA", "ml_engineer"))
