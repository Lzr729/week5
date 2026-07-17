from __future__ import annotations

import argparse
import json
from pathlib import Path

from .finalize import build_final_bundle, validate_final_bundle
from .stage9b import cli as cli9b
from .stage9c import cli as cli9c
from .stage9d import cli as cli9d


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 09 progressive automation")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build-model", "run-rules", "export-review", "import-review"):
        child = sub.add_parser(name, add_help=False)
        child.add_argument("args", nargs=argparse.REMAINDER)
    verify = sub.add_parser("verify-final")
    verify.add_argument("--bundle", required=True)
    combine = sub.add_parser("combine-final")
    combine.add_argument("--model-9b", required=True)
    combine.add_argument("--bundle-9c", required=True)
    combine.add_argument("--bundle-9d", required=True)
    combine.add_argument("--workbook-sha256", required=True)
    combine.add_argument("--tests-passed", type=int, required=True)
    combine.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build-model":
        return cli9b.main(args.args)
    if args.command == "run-rules":
        return cli9c.main(args.args)
    if args.command == "export-review":
        return cli9d.main(["export-review", *args.args])
    if args.command == "import-review":
        return cli9d.main(["import-review", *args.args])
    if args.command == "verify-final":
        bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
        failures = validate_final_bundle(bundle)
        print(json.dumps({"result": "PASS" if not failures else "FAIL", "failures": failures}, ensure_ascii=False, indent=2))
        return 0 if not failures else 1
    model = json.loads(Path(args.model_9b).read_text(encoding="utf-8"))
    bundle9c = json.loads(Path(args.bundle_9c).read_text(encoding="utf-8"))
    bundle9d = json.loads(Path(args.bundle_9d).read_text(encoding="utf-8"))
    output = build_final_bundle(model, bundle9c, bundle9d, final_workbook_sha256=args.workbook_sha256, tests_passed=args.tests_passed)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
