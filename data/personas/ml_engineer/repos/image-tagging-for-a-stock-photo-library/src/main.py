"""Image tagging for a stock-photo library (synthetic portfolio sample).

Core flow: a multi-label classifier fine-tuned from a pretrained backbone.
"""
import cv2
import torch
import torch.nn as nn
import onnxruntime as ort
import sys


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
