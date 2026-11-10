"""Defect detection on a bottling line (synthetic portfolio sample).

Core flow: a fine-tuned object detector exported for CPU inference on the line PC.
"""
import cv2
import torch
import torch.nn as nn
from ultralytics import YOLO
import cv2
import onnxruntime as ort


def run(config: dict) -> dict:
    """Entry point used by the scheduled job and the tests."""
    data = load(config["source"])
    result = process(data)
    report(result)
    return result
