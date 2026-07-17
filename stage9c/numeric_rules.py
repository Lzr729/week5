from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from . import RULE_SET_VERSION, __version__
from .trace import as_tokens, dedupe, trace_from_evidence

SUPPORTED_FORMULAS = {"ratio_pct", "product", "signed_sum", "unit_price", "share_to_capital"}


def D(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def recompute(validation: dict[str, Any]) -> Decimal:
    formula_type = validation["item"]["formula_type"]
    inputs = [row for row in validation["inputs"] if row.get("input_role") != "comparison"]
    values = [D(row.get("standardized_value")) for row in inputs]
    if any(value is None for value in values):
        raise ValueError("missing standardized numeric input")
    vals = [value for value in values if value is not None]
    with localcontext() as context:
        context.prec = 50
        if formula_type == "ratio_pct":
            by_role = {row["input_role"]: D(row.get("standardized_value")) for row in inputs}
            numerator, denominator = by_role.get("numerator"), by_role.get("denominator")
            if numerator is None or denominator in (None, Decimal("0")):
                raise ValueError("ratio requires nonzero denominator")
            return numerator / denominator * Decimal("100")
        if formula_type == "product":
            result = Decimal("1")
            for value in vals:
                result *= value
            return result
        if formula_type == "signed_sum":
            result = Decimal("0")
            for row in inputs:
                signed = D(row.get("signed_input_value"))
                if signed is None:
                    value = D(row.get("standardized_value"))
                    sign = D(row.get("sign")) or Decimal("1")
                    if value is None:
                        raise ValueError("signed sum input missing")
                    signed = value * sign
                result += signed
            return result
        if formula_type == "unit_price":
            by_role = {row["input_role"]: D(row.get("standardized_value")) for row in inputs}
            consideration = by_role.get("consideration_wan")
            shares = by_role.get("shares")
            if consideration is None or shares in (None, Decimal("0")):
                raise ValueError("unit price requires consideration and nonzero shares")
            return consideration * Decimal("10000") / shares
        if formula_type == "share_to_capital":
            shares = vals[0]
            return shares / Decimal("10000")
    raise ValueError(f"unsupported formula: {formula_type}")


def numeric_evaluations(model: dict[str, Any], run_id: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    validation_ids = {row["validation_id"] for row in model["numeric_validations"]}
    for row in model["numeric_validations"]:
        item, result = row["item"], row["result"]
        formula_type = item.get("formula_type")
        checks: list[dict[str, Any]] = []
        _check(checks, "S09-N001", formula_type in SUPPORTED_FORMULAS, formula_type, sorted(SUPPORTED_FORMULAS), "公式类型受控")
        missing_values = [x.get("input_id") for x in row["inputs"] if x.get("input_role") != "comparison" and D(x.get("standardized_value")) is None]
        _check(checks, "S09-N002", not missing_values, missing_values, [], "参与计算的标准化输入完整")
        try:
            calculated = recompute(row)
            calculation_error = None
        except Exception as exc:  # deterministic error capture
            calculated = None
            calculation_error = str(exc)
        expected = D(result.get("calculated_value_excel"))
        calc_tolerance = Decimal("1e-10") if expected is not None else Decimal("0")
        calc_match = calculated is not None and expected is not None and abs(calculated - expected) <= calc_tolerance
        _check(checks, "S09-N003", calc_match, _decimal_text(calculated), _decimal_text(expected), calculation_error or "确定性复算与上游计算值一致")

        comparison = D(result.get("comparison_value_excel"))
        difference = abs(calculated - comparison) if calculated is not None and comparison is not None else None
        upstream_difference = D(result.get("absolute_difference_excel"))
        diff_match = (difference is None and upstream_difference is None) or (
            difference is not None and upstream_difference is not None and abs(difference - upstream_difference) <= Decimal("1e-10")
        )
        _check(checks, "S09-N004", diff_match, _decimal_text(difference), _decimal_text(upstream_difference), "差异值由计算值与比较值确定")

        unit_ok, unit_note = _unit_check(row)
        _check(checks, "S09-N005", unit_ok, unit_note, "compatible", "单位与公式类型兼容")
        rounding_ok, rounding_observed = _rounding_check(row, calculated, comparison)
        _check(checks, "S09-N006", rounding_ok, rounding_observed, result.get("difference_classification"), "舍入区间与差异分类一致")

        unresolved_dependencies = []
        for input_row in row["inputs"]:
            source_id = str(input_row.get("source_value_id") or "")
            resolution = input_row.get("source_reference_resolution") or {}
            if resolution.get("status") == "UNRESOLVED":
                unresolved_dependencies.append(source_id)
            if source_id.startswith("VAL-") and source_id not in validation_ids:
                unresolved_dependencies.append(source_id)
        _check(checks, "S09-N007", not unresolved_dependencies, unresolved_dependencies, [], "派生校验依赖完整")

        separation_ok = result.get("calculated_value_excel") is not None and "comparison_value_excel" in result and "absolute_difference_excel" in result
        _check(checks, "S09-N008", separation_ok, list(result), ["calculated_value_excel", "comparison_value_excel", "absolute_difference_excel"], "原文比较值、计算值和差异值分层保存")

        if row["validation_id"] == "VAL-012":
            retained = difference == Decimal("0.00574") and result.get("final_conclusion") == "确认原文存在差异并保留"
            _check(checks, "S09-N009", retained, {"difference": _decimal_text(difference), "conclusion": result.get("final_conclusion")}, {"difference": "0.00574", "conclusion": "确认原文存在差异并保留"}, "CE-005披露差异不得被自动修正")
        else:
            _check(checks, "S09-N009", True, "not_applicable", "not_applicable", "仅适用于VAL-012")

        if row["validation_id"] == "VAL-044":
            _check(checks, "S09-N010", calculated == Decimal("1659535"), _decimal_text(calculated), "1659535", "CE-013十笔转让股份合计回归")
        else:
            _check(checks, "S09-N010", True, "not_applicable", "not_applicable", "仅适用于VAL-044")
        if row["validation_id"] == "VAL-045":
            _check(checks, "S09-N011", calculated == Decimal("8563.19"), _decimal_text(calculated), "8563.19", "CE-013十笔转让价款合计回归")
        else:
            _check(checks, "S09-N011", True, "not_applicable", "not_applicable", "仅适用于VAL-045")

        evidence_ids = dedupe(as_tokens(item.get("evidence_ids")) + as_tokens(result.get("evidence_ids")))
        trace = trace_from_evidence(model, evidence_ids)
        if result.get("original_excerpt"):
            trace["original_excerpts"] = dedupe(trace["original_excerpts"] + [str(result["original_excerpt"])])
        overall = "PASS" if all(check["result"] == "PASS" for check in checks) else "FAIL"
        output.append({
            "evaluation_id": f"S09-9C-NUM-{row['validation_id']}",
            "object_type": "NUMERIC_VALIDATION",
            "object_id": row["validation_id"],
            "event_ids": as_tokens(row.get("event_id")),
            **trace,
            "formula_type": formula_type,
            "recomputed_value": _decimal_text(calculated),
            "upstream_calculated_value": _decimal_text(expected),
            "comparison_value": _decimal_text(comparison),
            "absolute_difference": _decimal_text(difference),
            "checks": checks,
            "overall_result": overall,
            "derivation_type": "DETERMINISTIC_CALCULATION_AND_RULE_CLASSIFICATION",
            "program_version": __version__,
            "rule_set_version": RULE_SET_VERSION,
            "run_id": run_id,
            "review_required": result.get("manual_review_required") == "是" or overall == "FAIL",
            "review_status": "INHERITED_UPSTREAM_REVIEW" if result.get("manual_review_required") == "是" and overall == "PASS" else ("AUTO_PASS_PENDING_9C_ACCEPTANCE" if overall == "PASS" else "PENDING_9D_REVIEW"),
        })
    return output


def _unit_check(row: dict[str, Any]) -> tuple[bool, str]:
    formula = row["item"].get("formula_type")
    inputs = [x for x in row["inputs"] if x.get("input_role") != "comparison"]
    units = [str(x.get("standardized_unit") or "") for x in inputs]
    output_unit = str(row["result"].get("calculated_unit") or "")
    if formula == "ratio_pct":
        return len(units) >= 2 and units[0] == units[1] and output_unit == "%", f"{units}->{output_unit}"
    if formula == "unit_price":
        roles = {x.get("input_role"): x.get("standardized_unit") for x in inputs}
        return roles.get("consideration_wan") == "万元" and roles.get("shares") == "股" and output_unit == "元/股", f"{roles}->{output_unit}"
    if formula == "share_to_capital":
        return units == ["股"] and output_unit == "万元", f"{units}->{output_unit}"
    if formula == "signed_sum":
        return len(set(units)) == 1 and (not output_unit or output_unit == units[0]), f"{units}->{output_unit}"
    if formula == "product":
        return bool(units) and bool(output_unit), f"{units}->{output_unit}"
    return False, f"unsupported:{formula}"


def _rounding_check(row: dict[str, Any], calculated: Decimal | None, comparison: Decimal | None) -> tuple[bool, dict[str, Any]]:
    classification = row["result"].get("difference_classification")
    if comparison is None:
        return classification == "calculation_only", {"classification": classification, "comparison": None}
    if calculated is None:
        return False, {"classification": classification, "calculated": None}
    precision = int(row["result"].get("display_precision") or 0)
    half_unit = Decimal("0.5") * (Decimal("10") ** Decimal(-precision))
    difference = abs(calculated - comparison)
    exact = difference <= Decimal("1e-10")
    inside = difference <= half_unit + Decimal("1e-12")
    expected_classes = {"exact_match"} if exact else ({"rounding_consistent", "rounding_or_approx_consistent"} if inside else {"difference_detected"})
    return classification in expected_classes, {"difference": _decimal_text(difference), "half_rounding_unit": _decimal_text(half_unit), "classification": classification}


def _check(checks: list[dict[str, Any]], rule_id: str, passed: bool, observed: Any, expected: Any, note: str) -> None:
    checks.append({"rule_id": rule_id, "result": "PASS" if passed else "FAIL", "observed": observed, "expected": expected, "note": note})


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
