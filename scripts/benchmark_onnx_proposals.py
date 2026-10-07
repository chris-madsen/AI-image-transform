"""Benchmark one or more fixed-size local ONNX proposal exports."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

import numpy as np
from PIL import Image

from serve_onnx_proposals import OnnxProposalModel


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--sizes", nargs="+", type=int, default=[1024, 2048])
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    with Image.open(args.source) as image:
        source = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    results: list[dict[str, object]] = []
    for size in args.sizes:
        os.environ["MODEL_INPUT_SIZE"] = str(size)
        started = time.perf_counter()
        try:
            model = OnnxProposalModel()
            for _ in range(args.warmup):
                model.predict(source)
            timings = [model.predict(source)[1] for _ in range(args.runs)]
            results.append({
                "input_size": size,
                "provider": model.providers[0],
                "providers": list(model.providers),
                "runs": args.runs,
                "warmup": args.warmup,
                "inference_seconds": {
                    "min": min(timings),
                    "median": statistics.median(timings),
                    "max": max(timings),
                },
                "wall_seconds": time.perf_counter() - started,
                "status": "passed",
            })
        except Exception as exc:  # benchmark report must preserve failed sizes
            results.append({"input_size": size, "status": "failed", "error": str(exc), "wall_seconds": time.perf_counter() - started})
    print(json.dumps({"source": str(args.source), "results": results}, indent=2))
    return 0 if all(item["status"] == "passed" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
