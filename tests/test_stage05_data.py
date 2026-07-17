from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_DIR = ROOT / "data" / "json"


def load(name: str):
    return json.loads((JSON_DIR / name).read_text(encoding="utf-8"))


class Stage05DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.timeline = load("equity_timeline.json")
        cls.nodes = load("time_nodes.json")
        cls.calculations = load("calculations.json")
        cls.exclusions = load("exclusions.json")
        cls.review_items = load("review_items.json")

    def test_timeline_count_and_sequence(self):
        self.assertEqual(len(self.timeline), 17)
        self.assertEqual(
            [r["display_sequence"] for r in self.timeline],
            list(range(1, 18)),
        )

    def test_parent_events_are_not_duplicated(self):
        ids = {r["event_id"] for r in self.timeline}
        self.assertTrue({"CE-002", "CE-010", "CE-013"}.isdisjoint(ids))

    def test_evidence_traceability(self):
        for row in self.timeline:
            self.assertTrue(row["evidence_ids"])
            self.assertTrue(row["pdf_pages"])
            self.assertTrue(row["printed_pages"])

    def test_all_timeline_rows_approved(self):
        self.assertTrue(
            all(r["review_status"] == "已验收通过" for r in self.timeline)
        )

    def test_time_node_references_exist(self):
        node_ids = {r["time_node_id"] for r in self.nodes}
        for row in self.timeline:
            self.assertTrue(set(row["time_node_ids"]).issubset(node_ids))

    def test_calculation_references_exist(self):
        calculation_ids = {r["calculation_id"] for r in self.calculations}
        for row in self.timeline:
            self.assertTrue(set(row["calculation_ids"]).issubset(calculation_ids))

    def test_ce005_variance_retained(self):
        cal005 = next(r for r in self.calculations if r["calculation_id"] == "CAL-005")
        self.assertAlmostEqual(cal005["variance"], 0.00574, places=10)
        self.assertIn("阶段七", cal005["calculation_status"])

    def test_review_item_rv001_exists(self):
        rv001 = next(r for r in self.review_items if r["review_item_id"] == "RV-001")
        self.assertEqual(rv001["event_id"], "CE-005")
        self.assertIn("阶段七", rv001["status"])


if __name__ == "__main__":
    unittest.main()
