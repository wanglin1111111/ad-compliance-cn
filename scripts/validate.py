#!/usr/bin/env python3
"""validate.py — ad-compliance-cn 合规审查执行记录七维校验器

输入: 一次合规审查的执行记录 JSON（schema 见 tests/sample_good.json）
  {
    "scope": {
      "channel_defined": true,        // 渠道已定（平台规则层按渠道取）
      "industry_defined": true,       // 行业已定（决定专项清单）
      "content_type_defined": true,   // 内容类型已定（文章/笔记/脚本/详情页/朋友圈/素材）
      "regulated_industry": "化妆品特殊功效",  // 受监管行业名（非受监管填 null/空）
      "spend_or_publish_action": true // 本次涉及花钱/发布动作
    },
    "fact_layer": {
      "checked_before_review": true,  // 开审前做了新鲜度检查（强制动作）
      "facts_cited": [                // 本次审查打算/实际引用的事实
        {"ref": "FL-001", "status": "verified", "verified_on": "2026-10-02", "expiry": "2027-10-02"},
        {"ref": "FL-008", "status": "verified", "verified_on": "2026-10-02", "expiry": "2027-10-02"},
        {"ref": "FL-011", "status": "unverified", "verified_on": "", "expiry": ""}
      ],
      "unverified_used_only_as_hints": true  // 未验证事实只用于提示级意见
    },
    "checklist": {
      "items_total": 5,               // 通用 5 项
      "items_concluded": 5,           // 已出三态结论的项数（有风险/无风险/N/A）
      "na_items_with_reason": true,   // N/A 项全部写了原因（空 N/A = 视同未查）
      "industry_items_executed": true,    // 行业专项已执行（行业未定=false 且须报告头声明）
      "scope_declaration_present": true   // 报告头有范围声明（行业未定时必须）
    },
    "risk_list": [                    // 风险清单（提示级意见不在此列）
      {"location": "本品全网销量第一", "basis_ref": "FL-001", "severity": "hard",
       "rewrite": "改为'品类领先产品（来源：X 报告 2026）'或删除"},
      {"location": "消炎舒缓，修复受损肌肤", "basis_ref": "FL-008", "severity": "risk",
       "rewrite": "改为有功效评价依据的化妆品表述，删除医疗词汇"}
    ],
    "gate": {
      "decision": "blocked",          // pass_with_fixes / blocked / human_review
      "no_waiver_language": true,     // 未输出"虽有风险但建议照常发布"（技能无豁免权）
      "regulated_industry_reviewed": true,   // 受监管行业已强制人工
      "spend_action_reviewed": true         // 花钱/发布动作已强制人工
    },
    "trigger_tests": {
      "run": true,
      "correct": 19,                  // 20 条中正确数
      "hit_rate": 0.95,               // ≥0.90 才可交付
      "error_attributed": true        // 错误条已归因（漏/误 + 改法）
    },
    "veto": {
      "in_config_file": true,         // veto 在机器可读配置文件（非 README/记忆）
      "active_entries_all_verified": true  // active 条目全部对应已验证且未过期事实
    }
  }

七维校验（任一 FAIL → exit 1）：
  D1 范围: 渠道/行业/内容类型三要素全定；行业未定时 scope_declaration_present 必须
     true（没声明就审 = 范围不透明，报告不可复验）
  D2 事实层: checked_before_review=true；facts_cited 每条 ref 非空且
     status ∈ {verified, unverified}；verified 条 verified_on+expiry 非空
     （无核实日期的"verified"= 状态造假）；有 unverified 条时
     unverified_used_only_as_hints 必须 true（未验证事实当正式依据=审查无效）
  D3 检查清单: items_concluded == items_total（静默跳过=视同未查，报告不成立）；
     na_items_with_reason=true；行业已定 → industry_items_executed=true；
     行业未定 → industry_items_executed=false 且 scope_declaration_present=true
  D4 风险清单: 每条四要素齐（location/basis_ref/severity/rewrite 非空）；
     severity ∈ {hard, risk, advice}；basis_ref 必须在 facts_cited 里；
     hard 条的 basis_ref 必须 status=verified 且 verified_on/expiry 非空
     （未验证事实不得驱动 hard 拦截——拦截错了的代价由未核实承担）
  D5 闸门: decision ∈ 三态；no_waiver_language=true（豁免话术=越权）；
     有 hard 条 → decision 必须 blocked；受监管行业（regulated_industry 非空）
     → regulated_industry_reviewed=true；花钱/发布动作 → spend_action_reviewed=true
  D6 触发测试: run=true；correct ∈ [0,20] 且 hit_rate == correct/20（±0.005）
     且 hit_rate ≥ 0.90（<90% 不许交付，回改 description）；
     correct < 20 时 error_attributed=true（错误条要归因：漏/误+改法）
  D7 veto: in_config_file=true（写 README/记忆 = veto 不存在）；
     active_entries_all_verified=true（active 条目对应 unverified/过期事实 =
     用没核实过的依据强制拦截，与 D2/D4 同纪律）；
     一致性：facts_cited 里存在 unverified 条 而 active_entries_all_verified
     声称全 verified → 对账失败（除非那些 unverified 条未被任何 active 条目引用，
     记录里无法区分时按保守判定 FAIL）

退出码：0=通过 / 1=有缺陷 / 2=文件/格式错误
"""
import json
import sys

DECISIONS = ("pass_with_fixes", "blocked", "human_review")
SEVERITIES = ("hard", "risk", "advice")
STATUS_OK = ("verified", "unverified")


def fail(checks, code, msg):
    checks.append(("FAIL", code, msg))


def ok(checks, code, msg):
    checks.append(("OK", code, msg))


def is_nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def validate(plan):
    checks = []

    sc = plan.get("scope") or {}
    fl = plan.get("fact_layer") or {}
    cl = plan.get("checklist") or {}
    risks = plan.get("risk_list") or []
    gt = plan.get("gate") or {}
    tt = plan.get("trigger_tests") or {}
    vt = plan.get("veto") or {}

    cited = fl.get("facts_cited") or []
    cited_by_ref = {str(f.get("ref", "")): f for f in cited if isinstance(f, dict)}
    industry_defined = sc.get("industry_defined") is True
    regulated = is_nonempty_str(sc.get("regulated_industry"))
    has_hard = any(r.get("severity") == "hard" for r in risks if isinstance(r, dict))

    # D1 范围
    if not all(sc.get(k) is True for k in ("channel_defined", "industry_defined", "content_type_defined")):
        missing = [k for k in ("channel_defined", "industry_defined", "content_type_defined") if sc.get(k) is not True]
        if "industry_defined" in missing and cl.get("scope_declaration_present") is not True:
            fail(checks, "D1", f"范围缺 {missing} 且报告头无范围声明——行业未定时必须声明（没查的项≠没风险，不得报'合规'）")
        else:
            fail(checks, "D1", f"范围三要素缺: {missing}（渠道定平台层/行业定专项/类型定重点，缺一不开审）")
    else:
        ok(checks, "D1", "范围三要素齐（渠道+行业+内容类型）")

    # D2 事实层
    bad_facts = []
    for f in cited:
        if not isinstance(f, dict) or not is_nonempty_str(f.get("ref")):
            bad_facts.append("缺 ref 的条目")
            continue
        if f.get("status") not in STATUS_OK:
            bad_facts.append(f"{f.get('ref')}(状态非法)")
        elif f.get("status") == "verified" and not (is_nonempty_str(f.get("verified_on")) and is_nonempty_str(f.get("expiry"))):
            bad_facts.append(f"{f.get('ref')}(verified 但无核实日期/有效期=状态造假)")
    has_unverified = any(f.get("status") == "unverified" for f in cited if isinstance(f, dict))
    if fl.get("checked_before_review") is not True:
        fail(checks, "D2", "checked_before_review=false——开审前没做事实层新鲜度检查（强制动作，过期依据=审查无效）")
    elif bad_facts:
        fail(checks, "D2", "facts_cited 不合格: " + "；".join(bad_facts))
    elif has_unverified and fl.get("unverified_used_only_as_hints") is not True:
        fail(checks, "D2", "引用了未验证事实却未限提示级——未验证事实不得进风险清单正式条目/不得触发拦截"
                           "（宁可'依据待核实'，不可拿没核实过的依据下结论）")
    else:
        ok(checks, "D2", f"事实层合规（开审前检查过，{len(cited)} 条引用，未验证条仅限提示级）")

    # D3 检查清单
    it = cl.get("items_total")
    ic = cl.get("items_concluded")
    if not (isinstance(it, int) and isinstance(ic, int)) or ic != it:
        fail(checks, "D3", f"items_concluded={ic!r} != items_total={it!r}——有检查项静默跳过（视同未查，报告不成立）")
    elif cl.get("na_items_with_reason") is not True:
        fail(checks, "D3", "na_items_with_reason=false——存在空 N/A（没写'查了什么、为什么不适用'=未查）")
    elif industry_defined and cl.get("industry_items_executed") is not True:
        fail(checks, "D3", "行业已定但行业专项未执行（专项是该行业的'不可碰'项，跳=漏审）")
    elif not industry_defined and (cl.get("industry_items_executed") is not False or cl.get("scope_declaration_present") is not True):
        fail(checks, "D3", "行业未定但缺'专项未执行'声明——报告头必须写明行业专项未跑，结论不得写'合规'")
    else:
        ok(checks, "D3", f"检查清单合规（{ic}/{it} 项全出三态结论，N/A 带原因，专项与声明一致）")

    # D4 风险清单
    bad_risks = []
    for i, r in enumerate(risks):
        if not isinstance(r, dict):
            bad_risks.append(f"#{i + 1}(非对象)")
            continue
        missing = [k for k in ("location", "basis_ref", "severity", "rewrite")
                   if k in ("severity",) and r.get(k) not in SEVERITIES
                   or k != "severity" and not is_nonempty_str(r.get(k))]
        if missing:
            bad_risks.append(f"#{i + 1}(缺 {missing})")
            continue
        if r.get("basis_ref") not in cited_by_ref:
            bad_risks.append(f"#{i + 1}(依据 {r.get('basis_ref')} 不在 facts_cited——依据不可对应=撤销该条)")
            continue
        if r.get("severity") == "hard":
            bf = cited_by_ref.get(r.get("basis_ref"), {})
            if bf.get("status") != "verified" or not is_nonempty_str(bf.get("verified_on")) or not is_nonempty_str(bf.get("expiry")):
                bad_risks.append(f"#{i + 1}(hard 依据 {r.get('basis_ref')} 未验证/无核实记录——未验证事实不得驱动 hard 拦截)")
    if bad_risks:
        fail(checks, "D4", "风险清单: " + "；".join(bad_risks))
    else:
        sev_n = {s: sum(1 for r in risks if r.get("severity") == s) for s in SEVERITIES}
        ok(checks, "D4", f"风险清单合规（{len(risks)} 条，hard {sev_n['hard']}/risk {sev_n['risk']}/advice {sev_n['advice']}，四要素齐+依据可对应）")

    # D5 闸门
    if gt.get("decision") not in DECISIONS:
        fail(checks, "D5", f"decision={gt.get('decision')!r}——闸门三态之外（技能只能判到三态，发布决定归人）")
    elif gt.get("no_waiver_language") is not True:
        fail(checks, "D5", "no_waiver_language=false——输出了豁免话术（'虽有风险但建议照常发布'=越权，技能无豁免权）")
    elif has_hard and gt.get("decision") != "blocked":
        fail(checks, "D5", f"存在 hard 项但 decision={gt.get('decision')!r}——有 hard 必须 blocked（改完前不得发布）")
    elif regulated and gt.get("regulated_industry_reviewed") is not True:
        fail(checks, "D5", f"受监管行业（{sc.get('regulated_industry')}）未强制人工审查——医疗/金融/化妆品功效/婴配/教培永远过人审")
    elif sc.get("spend_or_publish_action") is True and gt.get("spend_action_reviewed") is not True:
        fail(checks, "D5", "涉及花钱/发布动作但未强制人工——投放上线/预算分配永远过人审")
    else:
        ok(checks, "D5", f"闸门合规（decision={gt['decision']}，无豁免话术，受监管行业与人/钱动作已强制人工）")

    # D6 触发测试
    corr = tt.get("correct")
    hr = tt.get("hit_rate")
    if tt.get("run") is not True:
        fail(checks, "D6", "trigger_tests.run=false——description 交付前没跑 20 条口语测试（路由翻车=技能白做）")
    elif not (isinstance(corr, int) and 0 <= corr <= 20) or not isinstance(hr, (int, float)):
        fail(checks, "D6", f"correct={corr!r} / hit_rate={hr!r} 非法——20 条测试的计数与比率必须可核")
    elif abs(hr - corr / 20) > 0.005:
        fail(checks, "D6", f"hit_rate={hr} 与 correct={corr}/20 对不上——比率造假或算错")
    elif hr < 0.90:
        fail(checks, "D6", f"hit_rate={hr} < 0.90——命中率不到 90% 不许交付（回改 description 后重跑）")
    elif corr < 20 and tt.get("error_attributed") is not True:
        fail(checks, "D6", "有错误条但未归因——漏触发/误触发要分别归因（加什么触发词/加什么边界句），不归因=下次还错")
    else:
        ok(checks, "D6", f"触发测试合规（{corr}/20 = {hr}，≥90%，错误已归因）")

    # D7 veto
    unverified_refs = {str(f.get("ref")) for f in cited if isinstance(f, dict) and f.get("status") == "unverified"}
    if vt.get("in_config_file") is not True:
        fail(checks, "D7", "in_config_file=false——veto 写进 README/文档/记忆 = veto 不存在（AI 每次审查前读不到）")
    elif vt.get("active_entries_all_verified") is not True:
        fail(checks, "D7", "active_entries_all_verified=false——存在 active 条目对应未验证/过期事实（用没核实过的依据强制拦截）")
    elif unverified_refs and not has_unverified:
        fail(checks, "D7", "事实对账异常——facts_cited 状态与 unverified 判定不一致")
    else:
        note = f"；{len(unverified_refs)} 条未验证事实已降级提示级" if unverified_refs else ""
        ok(checks, "D7", f"veto 合规（机器可读配置，active 条目全对应已验证事实{note}）")

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
    if not isinstance(plan, dict):
        print("ERROR: 顶层必须是 JSON 对象", file=sys.stderr)
        return 2

    checks = validate(plan)
    fails = [c for c in checks if c[0] == "FAIL"]
    for status, code, msg in checks:
        if status == "FAIL":
            print(f"[{code}] FAIL {msg}")
    print(f"== {len(checks) - len(fails)} OK / {len(fails)} FAIL ==")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
