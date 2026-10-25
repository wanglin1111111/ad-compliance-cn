"""ad-compliance-cn validate.py 的变异测试。

sample 里的 source_url 使用 RFC 2606 的 .invalid 占位域名；生产记录必须换成
法条/平台官方文档的真实 URL。

每个用例只改一个维度，断言校验器仍然给出预期退出码；这样 P0 规则被改坏时
测试会立刻变红，而不是靠人工读代码发现。
"""
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate.py"
GOOD = ROOT / "tests" / "sample_good.json"
BAD = ROOT / "tests" / "sample_bad.json"


def load_good():
    return json.loads(GOOD.read_text(encoding="utf-8"))


def run_plan(plan, tmp_path):
    path = tmp_path / "record.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def assert_rc(plan, expected, tmp_path, dimension=None):
    result = run_plan(plan, tmp_path)
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == expected, output
    if dimension:
        assert f"[{dimension}] FAIL" in result.stdout, output
    return result


def no_hard_good():
    """A valid record with no hard items, used to test the human-review gate."""
    plan = load_good()
    plan["risk_list"] = [r for r in plan["risk_list"] if r["severity"] != "hard"]
    plan["hint_only"] = []
    for item in plan["checklist"]["items"]:
        if item["id"] in ("absolute_claims", "efficacy_claims"):
            item["status"] = "clear"
    return plan


def test_sample_good_passes(tmp_path):
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(GOOD)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_sample_bad_fails(tmp_path):
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(BAD)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 1, result.stdout + result.stderr


def test_expired_fact_fails(tmp_path):
    plan = load_good()
    plan["fact_layer"]["facts_cited"][0]["expiry"] = "2020-01-01"
    assert_rc(plan, 1, tmp_path, "D2")


def test_invalid_date_fails(tmp_path):
    plan = load_good()
    plan["fact_layer"]["facts_cited"][0]["verified_on"] = "not-a-date"
    assert_rc(plan, 1, tmp_path, "D2")


def test_verified_fact_requires_source_url(tmp_path):
    plan = load_good()
    plan["fact_layer"]["facts_cited"][0]["source_url"] = ""
    assert_rc(plan, 1, tmp_path, "D2")


def test_platform_rule_expiry_over_90_days_fails(tmp_path):
    plan = load_good()
    today = date.today()
    plan["fact_layer"]["facts_cited"].append({
        "ref": "FL-TEST",
        "type": "platform_rule",
        "status": "verified",
        "verified_on": today.isoformat(),
        "expiry": (today + timedelta(days=120)).isoformat(),
        "source_url": "https://example.invalid/fl-test",
    })
    assert_rc(plan, 1, tmp_path, "D2")


def test_duplicate_ref_fails(tmp_path):
    plan = load_good()
    plan["fact_layer"]["facts_cited"].append(dict(plan["fact_layer"]["facts_cited"][0]))
    assert_rc(plan, 1, tmp_path, "D2")


def test_unverified_fact_does_not_require_source_url(tmp_path):
    plan = load_good()
    plan["fact_layer"]["facts_cited"].append({
        "ref": "FL-TEST",
        "type": "law",
        "status": "unverified",
        "verified_on": "",
        "expiry": "",
        "source_url": "",
    })
    assert_rc(plan, 0, tmp_path)


def test_regulated_industry_without_human_review_fails(tmp_path):
    plan = no_hard_good()
    plan["gate"]["decision"] = "pass_with_fixes"
    plan["gate"]["human_review_required"] = True
    plan["gate"]["human_review_reason"] = "受监管行业需人工"
    assert_rc(plan, 1, tmp_path, "D5")


def test_regulated_industry_with_human_review_passes(tmp_path):
    plan = no_hard_good()
    plan["gate"]["decision"] = "human_review"
    plan["gate"]["human_review_required"] = True
    plan["gate"]["human_review_reason"] = "受监管行业需人工"
    assert_rc(plan, 0, tmp_path)


def test_spend_action_without_human_review_fails(tmp_path):
    plan = no_hard_good()
    plan["scope"]["regulated_industry"] = ""
    plan["gate"]["decision"] = "pass_with_fixes"
    plan["gate"]["human_review_required"] = True
    plan["gate"]["human_review_reason"] = "投放动作需人工"
    assert_rc(plan, 1, tmp_path, "D5")


def test_unverified_basis_in_risk_list_fails(tmp_path):
    plan = load_good()
    plan["risk_list"].append({
        "check_id": "data_claims",
        "location": "未验证事实驱动",
        "basis_ref": "FL-011",
        "severity": "risk",
        "rewrite": "待核实",
    })
    assert_rc(plan, 1, tmp_path, "D4")


def test_unverified_basis_in_hint_only_passes(tmp_path):
    plan = load_good()
    assert_rc(plan, 0, tmp_path)


def test_missing_general_item_fails(tmp_path):
    plan = load_good()
    plan["checklist"]["items"] = [
        item for item in plan["checklist"]["items"] if item["id"] != "absolute_claims"
    ]
    plan["risk_list"] = [
        r for r in plan["risk_list"] if r["check_id"] != "absolute_claims"
    ]
    plan["hint_only"] = []
    assert_rc(plan, 1, tmp_path, "D3")


def test_na_without_reason_fails(tmp_path):
    plan = load_good()
    for item in plan["checklist"]["items"]:
        if item["id"] == "comparative_claims":
            item["status"] = "na"
            item["na_reason"] = ""
    assert_rc(plan, 1, tmp_path, "D3")


def test_risk_item_without_entry_fails(tmp_path):
    plan = load_good()
    for item in plan["checklist"]["items"]:
        if item["id"] == "comparative_claims":
            item["status"] = "risk"
    assert_rc(plan, 1, tmp_path, "D4")


def test_risk_check_id_must_be_risk_item(tmp_path):
    plan = load_good()
    plan["risk_list"][0]["check_id"] = "comparative_claims"
    assert_rc(plan, 1, tmp_path, "D4")


def test_veto_active_unverified_fails(tmp_path):
    plan = load_good()
    for entry in plan["veto"]["entries"]:
        if entry["id"] == "V-011":
            entry["status"] = "active"
    assert_rc(plan, 1, tmp_path, "D7")


def test_industry_undefined_with_declaration_passes(tmp_path):
    plan = load_good()
    plan["scope"]["industry_defined"] = False
    plan["scope"]["regulated_industry"] = ""
    plan["scope"]["spend_or_publish_action"] = False
    plan["checklist"]["industry_items_executed"] = False
    plan["checklist"]["scope_declaration_present"] = True
    plan["gate"]["human_review_required"] = False
    plan["gate"]["human_review_reason"] = ""
    plan["gate"]["regulated_industry_reviewed"] = False
    plan["gate"]["spend_action_reviewed"] = False
    assert_rc(plan, 0, tmp_path)


def test_nan_hit_rate_fails(tmp_path):
    plan = load_good()
    plan["trigger_tests"]["correct"] = 20
    plan["trigger_tests"]["hit_rate"] = float("nan")
    assert_rc(plan, 1, tmp_path, "D6")


def test_gate_must_be_object_exit_2(tmp_path):
    plan = load_good()
    plan["gate"] = "oops"
    assert_rc(plan, 2, tmp_path)
