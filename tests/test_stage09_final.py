from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

from artifact_tool import Blob, SpreadsheetFile
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stage09.finalize import stable_hash, validate_final_bundle
from stage09.stage9c.numeric_rules import recompute

BUNDLE_PATH = ROOT / "data" / "stage09_automation_bundle.json"
SCHEMA_PATH = ROOT / "schemas" / "stage09.schema.json"
WORKBOOK_PATH = ROOT / "deliverables" / "stage09_automation_final_approved.xlsx"


class Stage09FinalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.validations = {row["validation_id"]: row for row in cls.bundle["numeric_validations"]}

    def test_01_schema_validation(self) -> None:
        errors = list(Draft202012Validator(self.schema).iter_errors(self.bundle))
        self.assertEqual(errors, [], [error.message for error in errors])

    def test_02_final_validator_passes(self) -> None:
        self.assertEqual(validate_final_bundle(self.bundle), [])

    def test_03_final_status(self) -> None:
        self.assertEqual(self.bundle["metadata"]["status"], "FINAL_APPROVED")
        self.assertEqual(self.bundle["metadata"]["substage"], "9E")

    def test_04_source_record_counts(self) -> None:
        self.assertEqual(len(self.bundle["source_records"]), 1648)
        self.assertEqual(len(self.bundle["source_crosswalks"]), 1648)

    def test_05_source_stage_coverage(self) -> None:
        counts = Counter(row["source_stage"] for row in self.bundle["source_records"])
        self.assertEqual(dict(sorted(counts.items())), {1: 10, 2: 43, 3: 50, 4: 353, 5: 107, 6: 394, 7: 408, 8: 283})

    def test_06_input_artifacts_are_hashed(self) -> None:
        self.assertEqual(len(self.bundle["input_artifacts"]), 8)
        for row in self.bundle["input_artifacts"]:
            self.assertRegex(row["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(row["availability"], "AVAILABLE")

    def test_07_pdf_identity(self) -> None:
        row = next(x for x in self.bundle["input_artifacts"] if x["artifact_id"] == "SRC-PDF-001")
        self.assertEqual(row["sha256"], "1631a3ad350e58f5516f83b229f9ec3506e86b13b8e0973a59353c8d4f038e04")
        self.assertEqual(row["verification"]["page_count"], 443)

    def test_08_unified_object_counts(self) -> None:
        self.assertEqual(len(self.bundle["canonical_events"]), 26)
        self.assertEqual(len(self.bundle["canonical_entities"]), 45)
        self.assertEqual(len(self.bundle["canonical_evidence"]), 126)
        self.assertEqual(len(self.bundle["normalized_transactions"]), 63)
        self.assertEqual(len(self.bundle["normalized_snapshots"]), 216)

    def test_09_ce008_e04_evidence(self) -> None:
        row = next(x for x in self.bundle["canonical_evidence"] if x["evidence_id"] == "CE-008-E04")
        self.assertEqual(row["pdf_pages"], ["54"])
        self.assertEqual(row["printed_pages"], ["53"])
        self.assertIn("按1.1253:1折为4,000万股", row["original_excerpts"][0])

    def test_10_ce005_difference(self) -> None:
        row = self.validations["VAL-012"]
        self.assertEqual(row["result"]["absolute_difference_excel"], 0.00574)
        self.assertEqual(row["result"]["final_conclusion"], "确认原文存在差异并保留")

    def test_11_ce013_share_total(self) -> None:
        self.assertEqual(self.validations["VAL-044"]["result"]["calculated_value_excel"], 1659535)

    def test_12_ce013_consideration_total(self) -> None:
        self.assertEqual(self.validations["VAL-045"]["result"]["calculated_value_excel"], 8563.19)

    def test_13_automatic_evaluation_counts(self) -> None:
        auto = self.bundle["automation_results"]
        self.assertEqual(len(auto["numeric_evaluations"]), 55)
        self.assertEqual(len(auto["transaction_evaluations"]), 78)
        self.assertEqual(len(auto["pevc_evaluations"]), 143)

    def test_14_all_business_rules_pass(self) -> None:
        rows = self.bundle["automation_results"]["rule_results"]
        self.assertEqual(len(rows), 35)
        self.assertEqual({row["result"] for row in rows}, {"PASS"})

    def test_15_all_evaluations_have_trace(self) -> None:
        auto = self.bundle["automation_results"]
        rows = auto["numeric_evaluations"] + auto["transaction_evaluations"] + auto["pevc_evaluations"]
        self.assertEqual(len(rows), 276)
        for row in rows:
            for key in ("event_ids", "evidence_ids", "pdf_pages", "printed_pages", "original_excerpts"):
                self.assertTrue(row[key], (row["evaluation_id"], key))

    def test_16_not_disclosed_values_remain_null(self) -> None:
        rows = [x for x in self.bundle["pevc_results"]["investment_records"] if x["attributes"]["value_type"] == "NOT_DISCLOSED"]
        self.assertEqual(len(rows), 13)
        for row in rows:
            self.assertIsNone(row["attributes"]["shares_or_capital_value"])
            self.assertIsNone(row["attributes"]["cash_or_consideration_value"])

    def test_17_gp_edges_nonforming(self) -> None:
        rows = [x for x in self.bundle["pevc_results"]["path_edges"] if x["attributes"]["relationship_type"] in {"GENERAL_PARTNER", "GENERAL_PARTNER_EXECUTIVE"}]
        self.assertEqual(len(rows), 8)
        self.assertEqual({row["attributes"]["path_forming_flag"] for row in rows}, {"否"})

    def test_18_no_fuzzy_entity_mapping(self) -> None:
        self.assertTrue(all(row["mapping_method"] == "UPSTREAM_APPROVED_ID_AND_NAME_MAPPING_ONLY" for row in self.bundle["canonical_entities"]))

    def test_19_review_closure(self) -> None:
        self.assertEqual(len(self.bundle["review_actions"]), 17)
        self.assertEqual({row["validation_result"] for row in self.bundle["review_actions"]}, {"VALID"})
        self.assertEqual({row["review_status"] for row in self.bundle["review_actions"]}, {"已关闭"})

    def test_20_auto_results_preserved(self) -> None:
        self.assertTrue(all(row.get("before_auto_result") for row in self.bundle["review_actions"]))
        self.assertEqual({row["human_decision"] for row in self.bundle["review_actions"]}, {"确认自动结果"})

    def test_21_unknown_formula_rejected(self) -> None:
        row = copy.deepcopy(self.validations["VAL-001"])
        row["item"]["formula_type"] = "unsupported_formula"
        with self.assertRaises(ValueError):
            recompute(row)

    def test_22_zero_denominator_rejected(self) -> None:
        row = copy.deepcopy(self.validations["VAL-001"])
        for item in row["inputs"]:
            if item["input_role"] == "denominator":
                item["standardized_value"] = 0
        with self.assertRaises(ValueError):
            recompute(row)

    def test_23_forbidden_inference_mutation_detected(self) -> None:
        mutated = copy.deepcopy(self.bundle)
        row = next(x for x in mutated["pevc_results"]["investment_records"] if x["attributes"]["value_type"] == "NOT_DISCLOSED")
        row["attributes"]["cash_or_consideration_value"] = 0
        self.assertTrue(any(x["rule_id"] == "S09-G001" for x in validate_final_bundle(mutated)))

    def test_24_gp_path_mutation_detected(self) -> None:
        mutated = copy.deepcopy(self.bundle)
        row = next(x for x in mutated["pevc_results"]["path_edges"] if x["attributes"]["relationship_type"] == "GENERAL_PARTNER")
        row["attributes"]["path_forming_flag"] = "是"
        self.assertTrue(any(x["rule_id"] == "S09-G002" for x in validate_final_bundle(mutated)))

    def test_25_workbook_and_business_hash(self) -> None:
        wb = SpreadsheetFile.import_xlsx(Blob.load(str(WORKBOOK_PATH)))
        sheets = json.loads("[" + ",".join(line for line in wb.inspect({"kind": "sheet", "include": "id,name"}).ndjson.splitlines()) + "]")
        names = {row["name"] for row in sheets}
        self.assertIn("11_9E最终验收", names)
        workbook_hash = hashlib.sha256(WORKBOOK_PATH.read_bytes()).hexdigest()
        self.assertEqual(workbook_hash, self.bundle["run_manifest"]["final_workbook_sha256"])
        business_view = {
            "automation_results": self.bundle["automation_results"],
            "review_actions": self.bundle["review_actions"],
            "acceptance_checks": self.bundle["acceptance_checks"],
        }
        self.assertEqual(stable_hash(business_view), self.bundle["run_manifest"]["final_business_hash"])


if __name__ == "__main__":
    unittest.main()
