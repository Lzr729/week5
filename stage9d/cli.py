from __future__ import annotations

import argparse
import json
from pathlib import Path

from .outputs import export_review_workbook, import_review_decisions
from .review import apply_decisions, build_review_bundle


def parser() -> argparse.ArgumentParser:
    root=argparse.ArgumentParser(description="Stage 09 substage 9D human-review workflow")
    sub=root.add_subparsers(dest="command", required=True)
    exp=sub.add_parser("export-review")
    exp.add_argument("--input-9c", required=True)
    exp.add_argument("--output-bundle", required=True)
    exp.add_argument("--output-workbook", required=True)
    imp=sub.add_parser("import-review")
    imp.add_argument("--input-bundle", required=True)
    imp.add_argument("--input-workbook", required=True)
    imp.add_argument("--output-bundle", required=True)
    imp.add_argument("--output-actions", required=True)
    return root


def main(argv: list[str] | None=None) -> int:
    args=parser().parse_args(argv)
    if args.command=="export-review":
        bundle_9c=json.loads(Path(args.input_9c).read_text(encoding="utf-8"))
        review_bundle=build_review_bundle(bundle_9c)
        Path(args.output_bundle).write_text(json.dumps(review_bundle,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        export_review_workbook(bundle_9c,review_bundle,args.output_workbook)
        return 0
    review_bundle=json.loads(Path(args.input_bundle).read_text(encoding="utf-8"))
    decisions=import_review_decisions(args.input_workbook)
    output=apply_decisions(review_bundle,decisions)
    Path(args.output_bundle).write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    Path(args.output_actions).write_text(json.dumps({"metadata":output["metadata"],"review_actions":output["review_actions"],"summary":output["summary"]},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0 if output["summary"]["pending"]==0 and output["summary"]["invalid"]==0 else 1


if __name__=="__main__":
    raise SystemExit(main())
