from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .adapters import adapt_package
from .model import build_unified_model
from .provenance import inspect_pdf, register_file
from .validation import validate_model


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 09 substage 9B full-input unified model builder")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--stage12", required=True, help="Combined stage 1-2 accepted ZIP")
    parser.add_argument("--stage03", required=True)
    parser.add_argument("--stage04", required=True)
    parser.add_argument("--stage05", required=True)
    parser.add_argument("--stage06", required=True)
    parser.add_argument("--stage07", required=True)
    parser.add_argument("--stage08", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--exceptions-output", required=True)
    parser.add_argument("--registry-output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = {
        1: Path(args.stage12),
        2: Path(args.stage12),
        3: Path(args.stage03),
        4: Path(args.stage04),
        5: Path(args.stage05),
        6: Path(args.stage06),
        7: Path(args.stage07),
        8: Path(args.stage08),
    }
    stages = {stage: adapt_package(stage, path) for stage, path in paths.items()}

    pdf_verification = inspect_pdf(args.pdf)
    artifacts = [
        register_file(args.pdf, artifact_id="SRC-PDF-001", source_stage=None, artifact_role="PRIMARY_FACT_SOURCE", acceptance_status="PRIMARY_SOURCE_HASH_FROZEN", verification=pdf_verification),
        register_file(args.stage12, artifact_id="S09-IN-S01S02-ZIP", source_stage=1, covers_stages=[1, 2], artifact_role="UPSTREAM_ACCEPTED_PACKAGE", acceptance_status="FINAL_APPROVED", verification=_package_verification(stages[1], covers=[1, 2])),
        register_file(args.stage03, artifact_id="S09-IN-S03-ZIP", source_stage=3, artifact_role="UPSTREAM_ACCEPTED_PACKAGE", acceptance_status="FINAL_APPROVED", verification=_package_verification(stages[3])),
        register_file(args.stage04, artifact_id="S09-IN-S04-ZIP", source_stage=4, artifact_role="UPSTREAM_ACCEPTED_PACKAGE", acceptance_status="FINAL_APPROVED", verification=_package_verification(stages[4])),
        register_file(args.stage05, artifact_id="S09-IN-S05-ZIP", source_stage=5, artifact_role="UPSTREAM_ACCEPTED_PACKAGE", acceptance_status="FINAL_APPROVED", verification=_package_verification(stages[5])),
        register_file(args.stage06, artifact_id="S09-IN-S06-ZIP", source_stage=6, artifact_role="UPSTREAM_ACCEPTED_PACKAGE", acceptance_status="FINAL_APPROVED", verification=_package_verification(stages[6])),
        register_file(args.stage07, artifact_id="S09-IN-S07-ZIP", source_stage=7, artifact_role="UPSTREAM_ACCEPTED_PACKAGE", acceptance_status="FINAL_APPROVED", verification=_package_verification(stages[7])),
        register_file(args.stage08, artifact_id="S09-IN-S08-ZIP", source_stage=8, artifact_role="UPSTREAM_ACCEPTED_PACKAGE", acceptance_status="FINAL_APPROVED", verification=_package_verification(stages[8])),
    ]
    _attach_stage06_dependency_matches(artifacts, stages[6])

    model = build_unified_model(stages, artifacts)
    rules, exceptions, acceptance = validate_model(model, stages)
    model["rule_results"] = rules
    model["exceptions"] = exceptions
    model["acceptance_checks"] = acceptance
    failed = [row for row in rules if row["result"] == "FAIL"]
    blocking_open = [row for row in exceptions if row["status"] == "OPEN" and row["blocking_for_full_9b"]]
    model["metadata"]["available_scope_result"] = "PASS" if not failed else "FAIL"
    model["metadata"]["full_9b_result"] = "READY_FOR_USER_ACCEPTANCE" if not failed and not blocking_open else "BLOCKED"

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    exception_output = {
        "metadata": model["metadata"],
        "exceptions": exceptions,
        "summary": {
            "total": len(exceptions),
            "open": sum(row["status"] == "OPEN" for row in exceptions),
            "resolved": sum(row["status"].startswith("RESOLVED") for row in exceptions),
            "blocking_for_full_9b": sum(row["status"] == "OPEN" and row["blocking_for_full_9b"] for row in exceptions),
        },
    }
    Path(args.exceptions_output).write_text(json.dumps(exception_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.registry_output:
        registry = {"metadata": model["metadata"], "input_artifacts": artifacts}
        Path(args.registry_output).write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if failed else 0


def _package_verification(stage: Any, covers: list[int] | None = None) -> dict[str, Any]:
    audit = stage.metadata.get("package_audit", {})
    return {
        "covers_stages": covers or [stage.source_stage],
        "internal_audit_result": audit.get("result"),
        "internal_audit_issue_count": len(audit.get("issues", [])),
        "internal_audit_entries": len(audit.get("entries", [])),
    }


def _attach_stage06_dependency_matches(artifacts: list[dict[str, Any]], stage6: Any) -> None:
    dependencies = stage6.metadata.get("manifest", {}).get("upstream_dependencies", {}).get("upstream_archives", [])
    expected_by_stage: dict[int, str] = {}
    for item in dependencies:
        raw_stage = str(item.get("stage", ""))
        if raw_stage == "stage01_02":
            expected_by_stage[1] = str(item.get("archive_sha256"))
        else:
            digits = "".join(char for char in raw_stage if char.isdigit())
            if digits:
                expected_by_stage[int(digits)] = str(item.get("archive_sha256"))
    for artifact in artifacts:
        source_stage = artifact.get("source_stage")
        if source_stage in expected_by_stage:
            expected = expected_by_stage[source_stage]
            artifact["verification"]["stage06_declared_upstream_sha256"] = expected
            artifact["verification"]["stage06_dependency_hash_match"] = artifact["sha256"] == expected


if __name__ == "__main__":
    raise SystemExit(main())
