#!/usr/bin/env python3
"""validate.py — ad-compliance-cn 合规审查执行记录七维校验器

输入: 一次合规审查的执行记录 JSON（schema 见 tests/sample_good.json）
  {
    "scope": {
      "channel_defined": true, "industry_defined": true, "content_type_defined": true,
      "regulated_industry": "化妆品特殊功效",  // 非受监管填 null/""
      "spend_or_publish_action": true
    },
    "fact_layer": {
      "checked_before_review": true,
      "facts_cited": [{
        "ref": "FL-001", "type": "law", "status": "verified",
        "verified_on": "2026-10-02", "expiry": "2099-12-31",
        "source_url": "https://example.invalid/fl-001"
      }]
    },
    "checklist": {
      "items": [
        {"id": "absolute_claims", "status": "risk"},
        {"id": "efficacy_claims", "status": "risk"},
        {"id": "data_claims", "status": "risk"},
        {"id": "comparative_claims", "status": "clear"},
        {"id": "inducement_promises", "status": "clear"}
      ],
      "industry_items_executed": true,
      "scope_declaration_present": true
    },
    "risk_list": [{
      "check_id": "absolute_claims", "location": "本品全网销量第一",
      "basis_ref": "FL-001", "severity": "hard", "rewrite": "删除或改为有出处的表述"
    }],
    "hint_only": [{
      "check_id": "absolute_claims", "location": "平台规则可能有额外限制",
      "basis_ref": "FL-011", "note": "依据待核实，仅提示"
    }],
    "gate": {
      "decision": "blocked", "no_waiver_language": true,
      "human_review_required": true,
      "human_review_reason": "化妆品特殊功效 + 投放动作，需人工确认功效评价与数据出处",
      "regulated_industry_reviewed": true, "spend_action_reviewed": true
    },
    "trigger_tests": {"run": true, "correct": 19, "hit_rate": 0.95, "error_attributed": true},
    "veto": {
      "config_path": ".agents/ad-compliance-cn-veto.yaml",
      "entries": [{"id": "V-001", "fact_ref": "FL-001", "status": "active"}]
    }
  }

七维校验（任一 FAIL → exit 1）：
  D1 范围: 渠道/内容类型必须已定；行业已定，或行业未定但报告头声明且行业专项标记未执行。
  D2 事实层: 开审前检查；ref 不重复、type/status 合法；verified 必须有合法 ISO
     verified_on/expiry、source_url，且 verified_on ≤ 今天 ≤ expiry；platform_rule
     的 expiry-verified_on ≤ 90 天。有风险/提示条目时 facts_cited 不能为空。
  D3 检查清单: 五项通用检查（absolute_claims/efficacy_claims/data_claims/
     comparative_claims/inducement_promises）必须齐全；每项三态（risk/clear/na），
     na 必须写 na_reason；行业已定→专项执行，行业未定→专项未执行 + 报告头声明。
  D4 风险清单: 每条有 check_id/location/basis_ref/severity/rewrite；check_id 对应
     的检查项必须是 risk；依据必须是已验证且未过期事实（所有 severity，不只 hard）；
     每个 risk 检查项至少有一条 risk 或 hint_only 条目承载。
     hint_only 只能引用 unverified 事实，不得进入风险清单。
  D5 闸门: decision 三态；no_waiver_language=true；有 hard → blocked；
     受监管行业/花钱动作/声明需要人审 → human_review_reason 非空，且无 hard 时
     decision 必须是 human_review；受监管/花钱还要有 reviewed 标记。
  D6 触发测试: run=true；correct∈[0,20]；hit_rate 有限且 == correct/20（±0.005）；
     ≥0.90；correct<20 时 error_attributed=true。
  D7 veto: config_path 是 .yaml/.yml；entries 非空、id 不重复；每条 fact_ref 必须在
     facts_cited；active 条目必须对应 verified 且未过期事实；downgraded 条目必须
     对应 unverified 事实。

退出码：0=通过 / 1=有缺陷 / 2=文件/格式/结构错误。
"""
import json
import math
import sys
from datetime import date

DECISIONS = ("pass_with_fixes", "blocked", "human_review")
SEVERITIES = ("hard", "risk", "advice")
FACT_STATUS = ("verified", "unverified")
FACT_TYPES = ("law", "platform_rule", "industry_clause", "penalty_threshold")
ITEM_STATUS = ("risk", "clear", "na")
GENERAL_ITEMS = (
    "absolute_claims",
    "efficacy_claims",
    "data_claims",
    "comparative_claims",
    "inducement_promises",
)
VETO_STATUS = ("active", "downgraded")
MAX_PLATFORM_RULE_DAYS = 90


def fail(checks, code, msg):
    checks.append(("FAIL", code, msg))


def ok(checks, code, msg):
    checks.append(("OK", code, msg))


def is_nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def parse_iso(v):
    if not is_nonempty_str(v):
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def fact_is_current(fact, today):
    if fact.get("status") != "verified":
        return False
    start = parse_iso(fact.get("verified_on"))
    end = parse_iso(fact.get("expiry"))
    return bool(start and end and start <= today <= end)


def schema_error(plan):
    if not isinstance(plan, dict):
        return "顶层必须是 JSON 对象"
    for key in ("scope", "fact_layer", "checklist", "gate", "trigger_tests", "veto"):
        if not isinstance(plan.get(key), dict):
            return f"{key} 必须是对象"
    if not isinstance(plan.get("risk_list"), list):
        return "risk_list 必须是数组"
    if "hint_only" in plan and not isinstance(plan["hint_only"], list):
        return "hint_only 必须是数组"
    if not isinstance(plan["fact_layer"].get("facts_cited"), list):
        return "fact_layer.facts_cited 必须是数组"
    if not isinstance(plan["checklist"].get("items"), list):
        return "checklist.items 必须是数组"
    if not isinstance(plan["veto"].get("entries"), list):
        return "veto.entries 必须是数组"
    return None


def validate(plan):
    checks = []
    today = date.today()

    sc = plan["scope"]
    fl = plan["fact_layer"]
    cl = plan["checklist"]
    risks = plan.get("risk_list") or []
    hints = plan.get("hint_only") or []
    gt = plan["gate"]
    tt = plan["trigger_tests"]
    vt = plan["veto"]

    facts = fl.get("facts_cited") or []
    facts_by_ref = {
        str(f.get("ref")): f
        for f in facts
        if isinstance(f, dict) and is_nonempty_str(f.get("ref"))
    }
    items = cl.get("items")
    item_status = {
        str(i.get("id")): i.get("status")
        for i in items
        if isinstance(i, dict) and is_nonempty_str(i.get("id"))
    } if isinstance(items, list) else {}
    industry_defined = sc.get("industry_defined") is True
    regulated = is_nonempty_str(sc.get("regulated_industry"))
    spend = sc.get("spend_or_publish_action") is True
    has_hard = any(isinstance(r, dict) and r.get("severity") == "hard" for r in risks)

    # D1 范围
    channel = sc.get("channel_defined") is True
    content_type = sc.get("content_type_defined") is True
    declared = cl.get("scope_declaration_present") is True
    industry_run = cl.get("industry_items_executed")
    if not channel or not content_type:
        missing = [
            k
            for k, v in (("channel_defined", channel), ("content_type_defined", content_type))
            if not v
        ]
        fail(checks, "D1", f"范围缺 {missing}——渠道定平台层/内容类型定检查重点，缺一不开审")
    elif not industry_defined and not (declared and industry_run is False):
        fail(checks, "D1", "行业未定但没有声明或没有标记行业专项未执行——没查的项≠没风险")
    else:
        ok(checks, "D1", "范围合规（渠道+内容类型已定；行业已定或已声明未定）")

    # D2 事实层
    fact_errors = []
    has_risks = bool(risks or hints)
    if not facts and has_risks:
        fact_errors.append("有风险/提示条目但 facts_cited 为空——依据不可对应")
    seen = set()
    for i, f in enumerate(facts, 1):
        if not isinstance(f, dict):
            fact_errors.append(f"#{i} 非对象")
            continue
        ref = f.get("ref")
        if not is_nonempty_str(ref):
            fact_errors.append(f"#{i} 缺 ref")
            continue
        if ref in seen:
            fact_errors.append(f"{ref} 重复引用（同一 ref 只能出现一次）")
        seen.add(ref)
        typ = f.get("type")
        if typ not in FACT_TYPES:
            fact_errors.append(f"{ref} type={typ!r} 非法")
        status = f.get("status")
        if status not in FACT_STATUS:
            fact_errors.append(f"{ref} status={status!r} 非法")
            continue
        if status != "verified":
            continue
        start = parse_iso(f.get("verified_on"))
        end = parse_iso(f.get("expiry"))
        if not start or not end:
            fact_errors.append(f"{ref} verified 但 verified_on/expiry 不是合法 ISO 日期")
            continue
        if not is_nonempty_str(f.get("source_url")):
            fact_errors.append(f"{ref} verified 但缺 source_url")
        if start > today:
            fact_errors.append(f"{ref} verified_on={start.isoformat()} 在未来")
        if end < today:
            fact_errors.append(f"{ref} 已过期（expiry={end.isoformat()}）")
        if end < start:
            fact_errors.append(f"{ref} expiry 早于 verified_on")
        if typ == "platform_rule" and (end - start).days > MAX_PLATFORM_RULE_DAYS:
            fact_errors.append(f"{ref} 平台规则 expiry 超过 {MAX_PLATFORM_RULE_DAYS} 天")
    if fl.get("checked_before_review") is not True:
        fail(checks, "D2", "checked_before_review=false——开审前没做事实层新鲜度检查")
    elif fact_errors:
        fail(checks, "D2", "事实层不合格: " + "；".join(fact_errors))
    else:
        ok(checks, "D2", f"事实层合规（{len(facts)} 条引用；verified 日期/来源/时效均合法）")

    # D3 检查清单
    d3_errors = []
    if not isinstance(items, list) or not items:
        d3_errors.append("items 不能为空")
    else:
        ids = []
        for i, item in enumerate(items, 1):
            if not isinstance(item, dict):
                d3_errors.append(f"#{i} 非对象")
                continue
            item_id = item.get("id")
            status = item.get("status")
            if not is_nonempty_str(item_id):
                d3_errors.append(f"#{i} 缺 id")
                continue
            if item_id in ids:
                d3_errors.append(f"{item_id} 重复")
            ids.append(item_id)
            if status not in ITEM_STATUS:
                d3_errors.append(f"{item_id} status={status!r} 非法")
            elif status == "na" and not is_nonempty_str(item.get("na_reason")):
                d3_errors.append(f"{item_id} 标 N/A 但没写 na_reason")
        missing = [x for x in GENERAL_ITEMS if x not in ids]
        if missing:
            d3_errors.append(f"缺通用检查项: {missing}")
    if industry_defined:
        if cl.get("industry_items_executed") is not True:
            d3_errors.append("行业已定但行业专项未执行")
    else:
        if cl.get("industry_items_executed") is not False:
            d3_errors.append("行业未定但 industry_items_executed 不是 false")
        if not declared:
            d3_errors.append("行业未定但缺报告头声明")
    if d3_errors:
        fail(checks, "D3", "检查清单: " + "；".join(d3_errors))
    else:
        ok(checks, "D3", f"检查清单合规（{len(items)} 项，通用 5 项齐全，三态与 N/A 原因完整）")

    # D4 风险清单 + 提示级
    d4_errors = []
    if not isinstance(risks, list):
        d4_errors.append("risk_list 必须是数组")
        risks = []
    if not isinstance(hints, list):
        d4_errors.append("hint_only 必须是数组")
        hints = []
    for i, r in enumerate(risks, 1):
        if not isinstance(r, dict):
            d4_errors.append(f"风险#{i} 非对象")
            continue
        missing = [
            k
            for k in ("check_id", "location", "basis_ref", "severity", "rewrite")
            if (k == "severity" and r.get(k) not in SEVERITIES)
            or (k != "severity" and not is_nonempty_str(r.get(k)))
        ]
        if missing:
            d4_errors.append(f"风险#{i} 缺/非法 {missing}")
            continue
        check_id = r.get("check_id")
        if item_status.get(check_id) != "risk":
            d4_errors.append(f"风险#{i} check_id={check_id!r} 不是 risk 检查项")
        basis = facts_by_ref.get(str(r.get("basis_ref")))
        if not basis:
            d4_errors.append(f"风险#{i} 依据 {r.get('basis_ref')} 不在 facts_cited")
        elif basis.get("status") != "verified":
            d4_errors.append(f"风险#{i} 依据 {r.get('basis_ref')} 未验证——不得进风险清单")
        elif not fact_is_current(basis, today):
            d4_errors.append(f"风险#{i} 依据 {r.get('basis_ref')} 已过期/日期非法")
    for i, h in enumerate(hints, 1):
        if not isinstance(h, dict):
            d4_errors.append(f"提示#{i} 非对象")
            continue
        missing = [
            k
            for k in ("check_id", "location", "basis_ref", "note")
            if not is_nonempty_str(h.get(k))
        ]
        if missing:
            d4_errors.append(f"提示#{i} 缺 {missing}")
            continue
        check_id = h.get("check_id")
        if item_status.get(check_id) != "risk":
            d4_errors.append(f"提示#{i} check_id={check_id!r} 不是 risk 检查项")
        basis = facts_by_ref.get(str(h.get("basis_ref")))
        if not basis:
            d4_errors.append(f"提示#{i} 依据 {h.get('basis_ref')} 不在 facts_cited")
        elif basis.get("status") != "unverified":
            d4_errors.append(f"提示#{i} 的依据 {h.get('basis_ref')} 不是 unverified——已验证事实应进风险清单")
    for check_id, status in item_status.items():
        if status == "risk" and not any(
            isinstance(r, dict) and r.get("check_id") == check_id for r in risks
        ) and not any(isinstance(h, dict) and h.get("check_id") == check_id for h in hints):
            d4_errors.append(f"检查项 {check_id} 标 risk 但既无风险条目也无提示条目")
    if d4_errors:
        fail(checks, "D4", "风险清单: " + "；".join(d4_errors))
    else:
        sev_n = {s: sum(1 for r in risks if isinstance(r, dict) and r.get("severity") == s) for s in SEVERITIES}
        ok(
            checks,
            "D4",
            f"风险清单合规（{len(risks)} 条风险 + {len(hints)} 条提示；"
            f"hard/risk/advice={sev_n['hard']}/{sev_n['risk']}/{sev_n['advice']}；依据均可对应）",
        )

    # D5 闸门
    d5_errors = []
    decision = gt.get("decision")
    if decision not in DECISIONS:
        d5_errors.append(f"decision={decision!r} 不在三态")
    if gt.get("no_waiver_language") is not True:
        d5_errors.append("no_waiver_language=false（技能无豁免权）")
    if has_hard and decision != "blocked":
        d5_errors.append(f"存在 hard 但 decision={decision!r}，必须 blocked")
    must_human = regulated or spend or gt.get("human_review_required") is True
    if must_human:
        if not is_nonempty_str(gt.get("human_review_reason")):
            d5_errors.append("需要人工但缺 human_review_reason")
        if not has_hard and decision != "human_review":
            d5_errors.append(f"需要人工且无 hard，decision={decision!r} 必须 human_review")
        if regulated and gt.get("regulated_industry_reviewed") is not True:
            d5_errors.append(f"受监管行业（{sc.get('regulated_industry')}）缺 reviewed 标记")
        if spend and gt.get("spend_action_reviewed") is not True:
            d5_errors.append("花钱/发布动作缺 reviewed 标记")
    elif decision == "human_review" and not is_nonempty_str(gt.get("human_review_reason")):
        d5_errors.append("decision=human_review 但缺 human_review_reason")
    if d5_errors:
        fail(checks, "D5", "闸门: " + "；".join(d5_errors))
    else:
        ok(checks, "D5", f"闸门合规（decision={decision}，无豁免，人审要求已落实）")

    # D6 触发测试
    corr = tt.get("correct")
    hr = tt.get("hit_rate")
    if tt.get("run") is not True:
        fail(checks, "D6", "trigger_tests.run=false——交付前没跑 20 条口语测试")
    elif not isinstance(corr, int) or isinstance(corr, bool) or not 0 <= corr <= 20:
        fail(checks, "D6", f"correct={corr!r} 非法——必须是 0-20 的整数")
    elif not isinstance(hr, (int, float)) or isinstance(hr, bool) or not math.isfinite(hr):
        fail(checks, "D6", f"hit_rate={hr!r} 非法——必须是有限数值")
    elif abs(hr - corr / 20) > 0.005:
        fail(checks, "D6", f"hit_rate={hr} 与 correct={corr}/20 对不上")
    elif hr < 0.90:
        fail(checks, "D6", f"hit_rate={hr} < 0.90——命中率不到 90% 不许交付")
    elif corr < 20 and tt.get("error_attributed") is not True:
        fail(checks, "D6", "有错误条但未归因——漏/误触发要分别归因")
    else:
        ok(checks, "D6", f"触发测试合规（{corr}/20 = {hr}，错误已归因）")

    # D7 veto
    d7_errors = []
    config_path = vt.get("config_path")
    entries = vt.get("entries")
    if not is_nonempty_str(config_path) or not config_path.lower().endswith((".yaml", ".yml")):
        d7_errors.append("config_path 必须是 .yaml/.yml 路径")
    if not isinstance(entries, list) or not entries:
        d7_errors.append("veto.entries 不能为空")
    else:
        ids = set()
        for i, e in enumerate(entries, 1):
            if not isinstance(e, dict):
                d7_errors.append(f"veto#{i} 非对象")
                continue
            entry_id = e.get("id")
            fact_ref = e.get("fact_ref")
            status = e.get("status")
            if not is_nonempty_str(entry_id):
                d7_errors.append(f"veto#{i} 缺 id")
                continue
            if entry_id in ids:
                d7_errors.append(f"veto {entry_id} 重复")
            ids.add(entry_id)
            if status not in VETO_STATUS:
                d7_errors.append(f"veto {entry_id} status={status!r} 非法")
                continue
            if not is_nonempty_str(fact_ref):
                d7_errors.append(f"veto {entry_id} 缺 fact_ref")
                continue
            basis = facts_by_ref.get(str(fact_ref))
            if not basis:
                d7_errors.append(f"veto {entry_id} 的 {fact_ref} 不在 facts_cited")
            elif status == "active":
                if basis.get("status") != "verified":
                    d7_errors.append(f"veto {entry_id} active 但 {fact_ref} 未验证")
                elif not fact_is_current(basis, today):
                    d7_errors.append(f"veto {entry_id} active 但 {fact_ref} 已过期/日期非法")
            elif basis.get("status") != "unverified":
                d7_errors.append(f"veto {entry_id} downgraded 但 {fact_ref} 不是 unverified")
    if d7_errors:
        fail(checks, "D7", "veto: " + "；".join(d7_errors))
    else:
        ok(checks, "D7", f"veto 合规（{len(entries)} 条；active 均对应 verified 且未过期事实）")

    return checks


def main():
    if len(sys.argv) != 2:
        print("usage: python validate.py record.json", file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1], encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 无法读取/解析: {e}", file=sys.stderr)
        return 2
    error = schema_error(plan)
    if error:
        print(f"ERROR: 记录结构非法: {error}", file=sys.stderr)
        return 2
    try:
        checks = validate(plan)
    except (AttributeError, TypeError, ValueError) as e:
        print(f"ERROR: 记录结构非法: {e}", file=sys.stderr)
        return 2
    fails = [c for c in checks if c[0] == "FAIL"]
    for status, code, msg in checks:
        if status == "FAIL":
            print(f"[{code}] FAIL {msg}")
    print(f"== {len(checks) - len(fails)} OK / {len(fails)} FAIL ==")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
