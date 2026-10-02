# 从 marketingskills 的封装范式到中文营销缺口：ad-compliance-cn 的设计方法

> 上游：coreyhaines31/marketingskills（2026-10-02 实测 main：50 Skill / 50 evals.json / 349 eval case / CONTRIBUTING 500 行硬规范，MIT）
> 本文为 `ad-compliance-cn` 的方法论底座；可执行工作流见 `../SKILL.md`。

## 一、为什么选"广告法合规审查"作为营销域第一个技能

上游库偏海外 SaaS 营销栈。中文侧的缺口按价值排序有两个刚需（第十八篇文章判断，本次执行采信）：

1. **广告法合规审查**（极限词、绝对化用语、功效宣称）——选它做第一个，因为它是**所有中文营销内容的发布前必经门**：不管做 SEO、做内容、做投放，发布前都要过这道门。做它 = 给整个中文营销技能族装第一道闸门
2. 微信搜一搜/公众号内容 SEO——已有 `ai-seo-cn` 覆盖（第十八篇执行中已交付）

合规审查还天然承载了本次要搬进来的三条结构改进（见下），是三条改进的"全功能承载体"。

## 二、搬进来的三条结构改进（上游也缺的东西）

### 1. 事实层失效日期

```
合规审查的依据是法条与平台规则——恰好是"最容易过时"的两类内容：
  法规类：变化慢（年级）但一变就是全文换
  平台规则：变化快（月级）且常无公告直接改
过期框架比没框架更危险——它带着"看起来权威"的确定感把人带进坑。
设计：每条事实强制 verified_on + expiry 两字段；平台规则类 expiry ≤3 个月；
  状态只有两态（verified/unverified），无"我挺确定"中间态。
自我执行：本技能交付时的初始事实层 15 条全部标 unverified——
  交付者没有逐条核原文的记录，按自己的纪律不得伪造 verified_on。
  首用者核实一条升一条，未核实的事实只能出提示级意见，不得驱动 hard 拦截。
  （让"核实"有真实成本，而不是装饰。）
```

### 2. evals / 触发测试集

```
实测上游：50 个 evals.json、349 个 case，测的是技能加载后的输出质量
（prompt → expected_output + assertions）。
本文（第十八篇）指出的真正翻车点是路由：该触发时不触发、不该触发时乱触发。
设计：trigger-tests.md 的 20 条口语测试（10 应触发 + 10 应拒绝）只测路由——
  把 prompt 喂给"技能选择"环节（只看 frontmatter），记录命中率。
  ≥90% 才可交付；<90% 回改 description（漏→加触发词，误→加边界句，
  每次只改一类，改完重跑全套——同时改两类无法归因）。
与上游 evals 不互相替代：路由对 + 输出差 = 正文问题；路由错 + 输出对 = 白干。
```

### 3. 人工闸门

```
涉及花钱/发布的动作永远过人工——技能只判到三态（pass_with_fixes /
blocked / human_review），发布决定归人。
三条硬规则：技能无豁免权（永不输出"虽有风险但建议照常发布"）；
  受监管行业（医疗/金融/化妆品功效/婴配/教培）永远人审，不论判定结果；
  花钱/发布动作永远人审。
闸门状态写进报告最后一行，格式固定（validate.py D5 可校验）。
```

## 三、封装范式的执行对照（第十八篇"最小规格"三条硬规范）

| 硬规范 | 本技能执行 |
|---|---|
| name 与目录名一致的小写连字符 | `ad-compliance-cn` = 目录名 |
| description = 场景句 + 用户真实会说的触发词塞满 + 边界交接句 | 场景句（对中文营销内容做发布前合规审查）+ 触发词（能发吗/会封号吗/极限词/绝对化用语/审核不过…真实口语）+ 边界句（写文案不触发/SEO 走 ai-seo-cn/效果评估走 skill-eval） |
| 正文 500 行内 | SKILL.md 129 行 |
| 细节全下放 references/ | 4 份：fact-layer（事实层+失效纪律）/ channel-matrix（6 渠道矩阵）/ review-checklist（逐项判据+8 行业专项）/ trigger-tests（20 条路由测试） |
| 共享上下文 | `.agents/product-marketing.md`（Before Starting 双路径读取，与 ai-seo-cn 同一底座） |
| 停止条件 | 范围三要素缺一不开审 / 行业未定不报"合规" / 未验证事实不得驱动 hard / 闸门三态外不输出 |

## 四、实测核对（第十八篇数字 vs 2026-10-02 实测）

| 本文（第十八篇）数字 | 实测 | 判定 |
|---|---|---|
| 52,266 stars / 7,873 forks / 最后提交 10-01 | 52,268 / 7,874 / 2026-10-01T21:23Z | 一致（查询时点差 ±2） |
| 2026-01-15 建库 | created_at 2026-01-15T19:45Z | 证实 |
| "仓库现有 60 个技能" | skills/ 下 SKILL.md = 50（50 顶层目录） | **不符**——引用技能数须带测量口径与日期 |
| "上游有 251 个评测用例" | 50 个 evals.json，case 总数 349 | **不符**——同为数字滞后（方向是低估） |
| 九要素闭环 | 原文证实（Check cadence / Acts when / Self-check / State-idempotency / Stop-bail-out…）+ "missing a stop condition, a self-check, or its state handling is a liability" | 证实 |
| "价值在于分歧" + 强制反对方席位 | 原文证实（"The value isn't any single take — it's the disagreement" + "Always seat at least one designated dissenter"） | 证实 |
| 每技能先读 product-marketing.md | ai-seo/council 等 Before Starting 段原文证实 | 证实 |
| 500 行硬规范 + 细节下放 | CONTRIBUTING.md 原文证实 | 证实 |
| 脚手架压缩包 | 工作目录 4 个 zip 均非该脚手架（未收到） | 按最小规格+三条硬规范自补，不阻塞 |

## 五、接口

- 上游范式：marketingskills（封装范式）+ skill-lib-iterate（补位路径的方法论）
- 前置门关系：ad-compliance-cn 是 ai-seo-cn 发布内容的前置合规门；两技能共享 `.agents/product-marketing.md` 底座
- 评估接口：审查技能的回归样例 = 固定违规文本集（含极限词/功效/数据宣称典型违规句），关键要素 = 违规项全部被识别（与 skill-eval 的三件设计对齐）
- veto 活性绑定：`assets/ad-compliance-cn-veto.yaml` 12 条初始全 downgraded（事实层全 unverified），首用者核实事实层后对应条目恢复 active——**veto 的强度由事实的核实状态决定，而不是由写 veto 的人的信心决定**
