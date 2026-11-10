# defect-detection-on-a-bottling-line

Defect detection on a bottling line - a fine-tuned object detector exported for CPU inference on the line PC.

## Stack
- Computer vision
- PyTorch
- YOLO

## Quickstart
```
git clone <repo>
make install && make run
```

## Notes
Built for AquaPure Bottlers (synthetic) in 2024. Outcome: 98.2% recall on cracked caps at 25 frames per second on a CPU.
