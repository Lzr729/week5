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

C=Path(__file__).parents[1]/"outputs/candidates/candidate_event_packages.jsonl"
E=Path(__file__).parents[1]/"outputs/auto/events.jsonl"
def read_jsonl(path):
 return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
def test_candidate_packages():
 candidates=read_jsonl(C); events=read_jsonl(E)
 assert len(candidates)==9
 assert sum(x["source_type"]=="IMAGE_FLOWCHART" for x in candidates)==1
 assert all(x["gold_used_for_candidate_generation"] is False for x in candidates)
 covered=[event_id for row in candidates for event_id in row["downstream_event_ids"]]
 assert len(covered)==14 and len(set(covered))==14
 assert set(covered)=={row["auto_event_id"] for row in events}
 assert len(next(x for x in candidates if x["source_type"]=="IMAGE_FLOWCHART")["source_images"])==3
