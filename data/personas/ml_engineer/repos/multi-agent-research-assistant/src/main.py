"""Multi-agent research assistant (synthetic portfolio sample).

Core flow: a planner, researcher and writer agent with a human review step before export.
"""
import sys
from langgraph.graph import StateGraph, START, END
def retrieve_then_generate(question, index):
from fastapi import FastAPI
import redis


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
