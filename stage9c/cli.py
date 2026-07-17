from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import run_business_rules


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 09 substage 9C deterministic business-rule engine")
    parser.add_argument("--input-model", required=True, help="Formally approved 9B unified model JSON")
    parser.add_argument("--output", required=True)
    parser.add_argument("--exceptions-output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    model = json.loads(Path(args.input_model).read_text(encoding="utf-8"))
    bundle = run_business_rules(model)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    exception_document = {
        "metadata": bundle["metadata"],
        "exceptions": bundle["exceptions"],
        "summary": {
            "total": len(bundle["exceptions"]),
            "open": sum(row["status"] == "OPEN" for row in bundle["exceptions"]),
            "blocking": sum(row["status"] == "OPEN" and row["blocking_for_9c"] for row in bundle["exceptions"]),
        },
    }
    Path(args.exceptions_output).write_text(json.dumps(exception_document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if bundle["metadata"]["result"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
