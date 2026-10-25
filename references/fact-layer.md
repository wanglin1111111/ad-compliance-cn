# 事实层（Fact Layer）与失效日期纪律

> 本文件是 ad-compliance-cn 的**唯一依据源**。审查报告中每条风险的「依据」字段必须对应这里的一条事实 ref。
> 核心纪律：**事实有状态、有寿命。引用已失效或未验证的事实 = 审查无效。**

## 一、为什么事实层要带失效日期

```
合规审查的事实分两类，半衰期完全不同：
  法规类（广告法/行业法规）：变化慢（年级），但一变就是全文换（修法）
  平台规则类（小红书/抖音/微信审核口径）：变化快（月级），且常无公告直接改
  处罚/价格阈值类（罚款区间、备案门槛）：跟着法规走，但司法/执法口径会调
过期框架比没框架更危险——它带着"看起来权威"的确定感把人带进坑：
  你以为按最新口径审了，其实引用的是去年被改掉的条款。
所以每条事实强制两个字段：verified_on（什么时候核的原文）+ expiry（何时必须重核）。
```

## 二、事实条目格式

```yaml
- ref: FL-001                    # 稳定编号，报告引用它（不引用内容摘要）
  fact: "广告不得使用'国家级''最高级''最佳'等用语"
  type: law                      # law / platform_rule / industry_clause / penalty_threshold
  source: "《广告法》第九条第(三)项"
  verified_on: ""                # 核实日期（YYYY-MM-DD）；空 = 未核实
  expiry: ""                     # 必须重核的日期；未核实时按 type 默认寿命预估
  status: unverified             # verified / unverified（只有两态，无中间态）
  source_url: ""                 # 核实来源 URL（法条原文页/平台官方文档页）
  note: ""                       # 核实备注（口径变化说明、例外情形）
```

**状态双轨（与 ai-seo-cn 渠道映射表同构）**：
```
verified    = 有核实日期 + 来源 URL + 核实时 expiry ≥ 今天
unverified  = 其余一切（包括"我很确定它是对的"——没核实过就是没核实过）
未验证事实的用法：只能出「提示级」意见（"此处可能涉及 X，依据 FL-XXX 待核实"），
不得作为风险清单正式条目的依据，不得触发 hard 拦截。
机器口径：unverified 可以没有日期/source_url，但只能进 hint_only；
validate.py D4 会拒绝任何 severity 的 risk_list 引用 unverified 事实。
```

## 三、有效期默认规则（expiry 怎么设）

| type | 默认寿命 | 理由 |
|---|---|---|
| law | 12 个月 | 修法慢，但年度重核能兜住修法 |
| platform_rule | 3 个月 | 平台改口径不留公告的情况常见，短周期硬约束 |
| industry_clause | 12 个月 | 跟随法规 |
| penalty_threshold | 3 个月 | 执法口径调整快于立法 |

平台规则类事实**必须**设 ≤3 个月的 expiry。validate.py 的机器口径：
- verified 的 `verified_on`/`expiry` 必须是合法 ISO 日期，且 `verified_on ≤ 今天 ≤ expiry`；
- verified 必须有非空 `source_url`；
- `platform_rule` 的 `expiry - verified_on ≤ 90 天`；
- 同一 ref 不得重复；过期/非法日期 = D2 FAIL。

## 四、初始事实清单（2026-10-02 交付，**全部 unverified**）

> 为什么全标未验证：交付者没有逐条核原文的记录。这是本技能纪律的自我执行——
> 哪怕"我很确定广告法第九条这么写"，核实之前就是未验证。
> **首用流程**：开审前对本清单逐条核原文（法条查官方发布文本，平台规则查官方文档页），
> 核实一条填一条 verified_on + expiry + source_url，状态升 verified。
> 核实不了的（如平台内部口径查不到官方出处）保持 unverified，相关审查项只能出提示级意见。

```yaml
# ---- 法规类（law）----
- ref: FL-001
  fact: "广告不得使用'国家级''最高级''最佳'等用语（绝对化用语禁令）"
  type: law
  source: "《广告法》第九条第(三)项"
  status: unverified
- ref: FL-002
  fact: "非医疗、药品、医疗器械广告不得涉及疾病治疗功能，不得使用医疗用语或易使公众混淆的用语"
  type: law
  source: "《广告法》第十七条"
  status: unverified
- ref: FL-003
  fact: "广告中使用的数据、统计资料、调查结果、引用语等引证内容应当真实、准确，并表明出处"
  type: law
  source: "《广告法》第十一条"
  status: unverified
- ref: FL-004
  fact: "广告不得贬低其他生产经营者的商品或者服务"
  type: law
  source: "《广告法》第十三条"
  status: unverified
- ref: FL-005
  fact: "金融、投资广告不得含对未来效果、收益或者与其相关的情况作出保证性承诺，不得明示或暗示保本、无风险或保收益"
  type: law
  source: "《广告法》第二十五条"
  status: unverified
- ref: FL-006
  fact: "处方药不得在大众媒介发布广告；婴儿配方食品广告不得宣称替代母乳或满足全部营养需要"
  type: law
  source: "《广告法》第十五条/第二十条"
  status: unverified
- ref: FL-007
  fact: "普通食品广告不得声称保健功能，不得涉及疾病预防、治疗功能"
  type: law
  source: "《广告法》第十八条（保健食品）+ 食品广告监管规定"
  status: unverified
- ref: FL-008
  fact: "化妆品广告不得暗示具有医疗作用，不得明示或暗示治疗功效"
  type: industry_clause
  source: "《化妆品监督管理条例》及化妆品功效宣称评价规范"
  status: unverified
- ref: FL-009
  fact: "教育培训广告不得对升学、通过考试、获得学位学历或合格证书，或对教育效果作出明示或暗示的保证性承诺"
  type: industry_clause
  source: "《广告法》第二十四条"
  status: unverified
# ---- 处罚阈值类（penalty_threshold）----
- ref: FL-010
  fact: "使用绝对化用语的广告，处二十万元以上一百万元以下罚款，可吊销营业执照（具体适用口径以执法实践为准）"
  type: penalty_threshold
  source: "《广告法》第五十七条（口径待核实）"
  status: unverified
# ---- 平台规则类（platform_rule，expiry ≤3 个月）----
- ref: FL-011
  fact: "小红书对医疗/健康功效类内容审核从严，笔记含疾病治疗暗示易被限流/删帖（口径待核官方文档）"
  type: platform_rule
  source: "小红书社区规范（官方文档待核）"
  status: unverified
- ref: FL-012
  fact: "微信生态（公众号/朋友圈）对诱导分享（转发领奖品/集赞解锁）有明确限制"
  type: platform_rule
  source: "微信外部链接/运营规范（官方文档待核）"
  status: unverified
- ref: FL-013
  fact: "抖音电商广告素材与落地页一致性要求，素材宣称须在商品页可对应（口径待核官方文档）"
  type: platform_rule
  source: "抖音电商广告规范（官方文档待核）"
  status: unverified
- ref: FL-014
  fact: "视频号广告审核口径（待核）"
  type: platform_rule
  source: "视频号运营规范（官方文档待核）"
  status: unverified
- ref: FL-015
  fact: "百度推广/百家号内容审核口径（待核）"
  type: platform_rule
  source: "百度营销规范（官方文档待核）"
  status: unverified
```

## 五、核实流程（首用与重核通用）

```
1. 打开 source 指向的官方原文（法条：全国人大/政府门户发布文本；
   平台规则：平台官方文档中心页面，不看转述/自媒体解读）
2. 逐字对照 fact 字段：
   一致 → 填 verified_on=今天，expiry=今天+type 默认寿命，
     填 source_url，status→verified
   不一致 → 改 fact 为原文表述（以原文为准），再按上一条走
   查不到官方原文 → 保持 unverified，note 写"官方原文不可得，依据自媒体转述"
3. 更新记录追加一行（见下）
4. 平台规则类每次核实时额外检查：有无新版本公告/规则更新页
```

## 六、更新记录（追加式，不删旧行）

```markdown
# 事实层更新记录
| 日期 | ref | 动作 | 说明 |
|---|---|---|---|
| 2026-10-02 | 全部 | 初始化 | 交付时全 unverified（交付者无核实记录） |
| （首用者补） | FL-001 | 升级 verified | 核实《广告法》第九条原文，expiry 2027-10-02 |
```

## 七、与 veto list 的接口

```
veto 条目（assets/ad-compliance-cn-veto.yaml）每条带 fact_ref。
审查记录里的 `veto.entries` 由 validate.py 强制：
  fact_ref 对应事实 status=verified 且未过期 → 条目 active（可触发 hard 拦截）
  fact_ref 对应事实 unverified → 条目 downgraded（只出提示，不 hard 拦截）
  active 指向 unverified/过期事实 = D7 FAIL。
  注意：validator 校验的是审查记录里的 entries，不读 YAML 本体；
  记录 entries 与配置文件是否一致，仍需人工对账。
  设计意图：未核实的事实不能驱动强制拦截——
  拦截错了的代价（误拦合规内容/漏放风险）都由未核实承担，
  让"核实"这件事有真实成本，而不是装饰。
```
