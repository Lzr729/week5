from __future__ import annotations
import json
from pathlib import Path

def load_vision_output(path: str | Path) -> dict:
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    required={"model","input_images","events"}
    missing=required-set(data)
    if missing: raise ValueError(f"missing vision fields: {sorted(missing)}")
    return data

def validate_no_open_review(bundle: dict) -> None:
    if bundle["metadata"].get("open_review_items") != 0:
        raise ValueError("open review items remain")
