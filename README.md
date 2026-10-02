# ad-compliance-cn

中文营销内容的广告法合规审查：对公众号文章、小红书笔记、抖音/视频号脚本、商品详情页、朋友圈文案、投放素材做**发布前审查**，输出风险清单（条款依据 + 严重度 + 可照抄的改写建议）与闸门判定。

一句话：**事实层带状态与寿命（verified_on + expiry），未验证的事实只能出提示级意见、不得驱动 hard 拦截；范围三要素缺一不开审；风险清单四要素齐且依据可对应；闸门三态（pass_with_fixes / blocked / human_review），技能无豁免权、受监管行业与人/钱动作永远过人工。**

## 为什么是"营销域第一个技能"

- 上游 marketingskills（50 Skill，MIT）偏海外 SaaS 营销栈；中文侧两个刚需缺口中，合规审查是**所有中文营销内容的发布前必经门**——做 SEO、做内容、做投放，发布前都要过这道门
- 它是三条结构改进（事实层失效日期 / 20 条触发测试 / 人工闸门）的全功能承载体，也是 `ai-seo-cn` 发布内容的前置合规门

## 与上游范式的关系

封装范式源自 marketingskills（SKILL.md frontmatter 触发词 + 判断流程 / references 细节下放 / 共享上下文 / 停止条件 + 500 行硬规范），本技能在范式之上内置三条上游也缺的结构改进：

| 改进 | 设计 |
|---|---|
| 事实层失效日期 | 每条依据（法条/平台规则/行业条款）强制 verified_on + expiry；平台规则 ≤3 个月；状态两态（verified/unverified）；**初始 15 条事实全标 unverified**（交付者无核实记录，按自己的纪律不伪造）——首用者核原文后逐条升级 |
| 20 条触发测试 | 路由验证（10 应触发 + 10 应拒绝），只测 frontmatter 够不够让 Agent 选对技能；命中率 <90% 回改 description，不许交付；与上游 evals（50 文件 349 case，测输出质量）不互相替代 |
| 人工闸门 | 技能只判三态，发布决定归人；技能无豁免权；受监管行业（医疗/金融/化妆品功效/婴配/教培）永远人审；花钱/发布动作永远人审 |

## 安装

复制本目录到 `~/.agents/skills/`（或你的 Skill 加载路径）。依赖：

- `.agents/product-marketing.md` 产品上下文底座（行业字段决定专项检查清单）
- `assets/ad-compliance-cn-veto.yaml` 放 `.agents/` 下（veto 必须在 AI 每次审查前读得到的位置）

**首用流程（一次性）**：开审前对 `references/fact-layer.md` 的 15 条初始事实逐条核原文（法条查官方发布文本，平台规则查官方文档页），核实一条填一条 verified_on/expiry/source_url 并升 verified；对应 veto 条目从 downgraded 恢复 active。未核实完之前，相关审查项只能出提示级意见。

## 自检

```bash
python scripts/validate.py tests/sample_good.json   # 必须 exit 0
python scripts/validate.py tests/sample_bad.json    # 必须 exit 1
```

## 结构

```
SKILL.md                              工作流入口（诚实性总纪律 + 五步：定范围→事实层新鲜度检查→执行清单→风险清单→闸门判定 + 10 条硬规则，129 行 < 500 行规范）
references/fact-layer.md              事实层（唯一依据源）：条目格式（ref/type/source/verified_on/expiry/status/source_url）、有效期规则（法规 12 月/平台规则 3 月/处罚阈值 3 月）、初始 15 条事实清单（全 unverified）、核实流程、更新记录格式、与 veto 的活性接口
references/channel-matrix.md          6 渠道矩阵（小红书/公众号含搜一搜/抖音/视频号/百度/私域）×（法规层共性 + 平台规则层差异 + 审核口径观察状态）；渠道专项检查重点；核实排期（P0 主力渠道先核）；维护纪律（观察列与依据列分开写）
references/review-checklist.md        通用 5 项逐项判据（绝对化用语的 4 类例外/功效宣称的行业边界/数据宣称的出处要求/对比宣称/诱导承诺）+ 8 行业专项"不可碰"项 + N/A 原因标准写法（空 N/A=视同未查）+ 严重度判定与升级规则
references/trigger-tests.md           20 条路由测试（10 应触发口语变体 + 10 应拒绝相邻域）、怎么跑（只喂 frontmatter）、命中率口径（≥90% 交付）、留档格式、与上游 evals 的区别、<90% 时的 description 修改法（每次只改一类）
assets/ad-compliance-cn-veto.yaml     机器可读 veto：12 条（绝对化/医疗化/数据无出处/贬损竞品/收益承诺/处方药婴配/食品保健化/化妆品医疗化/教培承诺/诱导分享/小红书功效/素材落地页一致性），每条带 fact_ref，初始全 downgraded（事实层 unverified），核实后恢复 active；human_gate 段（受监管行业+花钱发布动作强制人审）
scripts/validate.py                   审查执行记录七维校验器（exit 0/1/2）：D1 范围三要素+行业未定声明 / D2 事实层新鲜度（verified 必须有核实日期=防状态造假，未验证只能提示级）/ D3 清单无静默跳过 / D4 风险四要素+依据可对应+未验证不得 hard / D5 闸门（有 hard 必 blocked、受监管行业必人审、无豁免话术）/ D6 触发测试 ≥90%+比率对账+错误归因 / D7 veto 进配置+active 条目全对已验证事实
tests/sample_good.json                通过基准（三要素齐+化妆品受监管行业 / 3 verified + 1 unverified 且仅限提示级 / 5 项全出结论 / 3 条风险四要素齐（2 hard 1 risk，依据全 verified）/ 有 hard → blocked + 受监管行业人审 + 花钱动作人审 / 19/20=0.95 / veto 进配置+active 全 verified）
tests/sample_bad.json                 拦截基准(行业未定+类型未定且无声明 / 没做新鲜度检查+verified 无核实日期+未验证事实当正式依据 / 5 项只出 3 项结论+空 N/A / 硬依据 FL-001 无核实记录+FL-005 未验证驱动 hard+FL-099 幽灵依据+severity=severe 非法+rewrite 空话 / 有 hard 却 pass_with_fixes+豁免话术 / 14/20=0.7 未归因 / veto 没进配置+active 未全 verified)
docs/methodology.md                   设计方法全文（选品理由 + 三条结构改进设计 + 范式执行对照 + 第十八篇数字实测核对表 + 接口）
```

## 相关

- 上游范式：`coreyhaines31/marketingskills`（MIT，2026-10-02 实测：50 Skill / 50 evals.json / 349 case / 500 行硬规范）
- 方法论：`skill-lib-iterate`（本技能是其"补位路径"在营销域的第一个实例）
- 下游：`ai-seo-cn`（本技能是其发布内容的前置合规门，共享 `.agents/product-marketing.md` 底座）
- 效果评估：`skill-eval`（审查技能的回归样例=固定违规文本集）
