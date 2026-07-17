from __future__ import annotations
import json
from pathlib import Path

def verify_bundle(path: str | Path) -> dict:
    b=json.loads(Path(path).read_text(encoding="utf-8"))
    assert len(b["events"])==14
    assert len(b["transaction_legs"])==48
    assert len(b["snapshots"])==15
    assert len(b["snapshot_holdings"])==201
    assert len(b["pevc_entities"])==45
    assert b["metadata"]["open_review_items"]==0
    return {"status":"PASS","counts":{k:len(b[k]) for k in ["events","transaction_legs","snapshots","snapshot_holdings","numeric_checks","pevc_entities","investment_records","path_edges"]}}
