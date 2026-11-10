"""Semantic product search (synthetic portfolio sample).

Core flow: embedding search over product text with a keyword fallback.
"""
def retrieve_then_generate(question, index):
import sys
from pinecone import Pinecone
from fastapi import FastAPI


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
