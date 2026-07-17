import json
from pathlib import Path
B=Path(__file__).parents[1]/"final/301563_raw_pdf_full_automation_bundle.json"
def load(): return json.loads(B.read_text(encoding="utf-8"))
def test_counts():
 b=load(); assert len(b["events"])==14; assert len(b["transaction_legs"])==48; assert len(b["snapshots"])==15; assert len(b["snapshot_holdings"])==201
def test_no_open_review(): assert load()["metadata"]["open_review_items"]==0
def test_ce005_difference():
 b=load(); rows=[x for x in b["numeric_checks"] if x.get("event_id")=="CE-005" or "CE-005" in str(x)]
 assert rows
def test_pevc_counts():
 b=load(); assert len(b["pevc_entities"])==45; assert len(b["investment_records"])==33; assert len(b["path_edges"])==65
def test_metrics():
 m=load()["comparison_metrics"]; assert m["events"]["recall"]==1.0; assert m["snapshots"]["holding_exact_rate"]==1.0
