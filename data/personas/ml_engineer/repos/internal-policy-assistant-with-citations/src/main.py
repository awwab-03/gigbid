"""Internal policy assistant with citations (synthetic portfolio sample).

Core flow: hybrid retrieval over chunked policies with page-level citations and a refusal when nothing matched.
"""
import sys
def retrieve_then_generate(question, index):
from langchain_core.prompts import ChatPromptTemplate
from openai import OpenAI
import faiss
from fastapi import FastAPI


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
