from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .common import sha256_file, write_json, write_jsonl
from .evaluator import evaluate
from .extractor import events_to_dicts, extract_events, extract_snapshots, extract_transaction_legs, render_review_images
from .locator import locate_ranges, ranges_to_dicts
from .pdf_reader import page_records_to_dicts, read_pdf


def _write_page_profile(path: Path, rows: list[dict]) -> None:
    fields = ["pdf_page", "printed_page", "text_char_count", "image_count", "text_layer_status", "parser_used", "text_sha256"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})


def run(args: argparse.Namespace) -> dict:
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    doc, pages = read_pdf(args.pdf)
    ranges = locate_ranges(pages)
    history = next(r for r in ranges if r.range_id == "R-HISTORY")
    events, review_items = extract_events(pages, history.start_pdf_page, history.end_pdf_page)
    event_dicts = events_to_dicts(events)
    legs = extract_transaction_legs(pages, events)
    snapshots, holdings = extract_snapshots(pages)
    rendered = render_review_images(doc, review_items, args.review_images)

    profile = page_records_to_dicts(pages)
    _write_page_profile(out / "page_profile.csv", profile)
    write_json(out / "located_sections.json", ranges_to_dicts(ranges))
    write_jsonl(out / "auto_events.jsonl", event_dicts)
    write_jsonl(out / "auto_transaction_legs.jsonl", legs)
    write_jsonl(out / "auto_snapshots.jsonl", snapshots)
    write_jsonl(out / "auto_snapshot_holdings.jsonl", holdings)
    write_jsonl(out / "manual_review_queue.jsonl", review_items)
    write_json(out / "review_images_manifest.json", rendered)

    metrics = None
    if args.gold:
        metrics = evaluate(event_dicts, legs, holdings, args.gold, out / "comparison")
    result = {
        "program_version": "0.1.0",
        "rule_set_version": "raw-pdf-v0.1.0",
        "pdf_file": Path(args.pdf).name,
        "pdf_sha256": sha256_file(args.pdf),
        "gold_file": Path(args.gold).name if args.gold else None,
        "gold_sha256": sha256_file(args.gold) if args.gold else None,
        "extraction_boundary": "PDF-only extraction; gold is loaded only by evaluator after outputs are written",
        "counts": {
            "pdf_pages": len(pages),
            "located_ranges": len(ranges),
            "auto_events": len(event_dicts),
            "auto_extracted_events": sum(1 for e in event_dicts if e["review_status"] == "AUTO_EXTRACTED"),
            "review_routed_event_clusters": sum(1 for e in event_dicts if e["review_status"] == "REVIEW_REQUIRED"),
            "transaction_legs": len(legs),
            "snapshots": len(snapshots),
            "snapshot_holding_rows": len(holdings),
            "review_items": len(review_items),
        },
        "metrics": metrics,
    }
    write_json(out / "run_summary.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="301563 raw-PDF-first extraction")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--review-images", required=True)
    parser.add_argument("--gold")
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
