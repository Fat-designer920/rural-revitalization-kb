# Prompt 手册

> 完整代码：`scripts/prompts/prompt_templates.py`
>
> 当前版本:`PROMPT_VERSION = "v2.3.7"`(v2.3.5-part2-hotfix1 — **5 个 _EXTRACT_BASE 老 1.X-5.X 编号清单整行删除**(立规则 9 第 23 次应验同根:prompt 硬编码 1.X 体系与 tag_config.LAYER1_TAGS 真实 A/B/C/D... 体系完全两个版本,F5 v2.3.5-part2 修了"格式不一致"但没修"体系不一致")— `_build_tag_reference()` 注入的 LAYER1_TAGS 真实清单是唯一真相;5 处字段说明"如1.1" → "从 LAYER1 清单中选";PRE_ANALYSIS 的 1.X-5.X 体系说明改"以三层标签体系为准";一套 prompt 同时喂 V4-Pro thinking 主链 + 硅基 V4-Pro 镜像兜底)
>
> 本手册记录所有 Prompt 的**接口契约**（输入占位符 / 输出结构 / 硬约束）。完整文本见代码，本文不复制冗长 Prompt 正文。

---

## 一、Prompt 清单（31 个）

### 提取类（R1，5 个）

> 实际变量为 `_POLICY_EXTRACT_BASE` 等内部 BASE，通过 `get_extraction_prompt(content_type)` 动态拼接共享策略块后输出。
>
> **v2.3.4 输出形态升级:JSON Lines**(原 `{"knowledge_points":[...]}` 嵌套数组形态废止)
> - 每行 1 个独立完整的 KP JSON 对象,行间换行符分隔
> - 最后一行(可选)输出元数据:`{"_meta":true,"file_summary":"...","extraction_notes":"..."}`
> - **截断容忍度**:数组形态 = 截断丢全部,JSON Lines = 截断只丢最后 1 行
> - **续写场景**:已生成行 + 最后一行不完整作为 prefix → 走 `client.chat_continue_with_prefix()`(beta 端点 + V3 默认)
> - 5 个 BASE 内禁止输出:`{"knowledge_points":[...]}` 数组结构、```代码块、解释文字
> - 字段集合不变(13 个核心字段 + 三层标签 + practical_insights),仅改包装

| 逻辑名 | 用途 |
|--------|------|
| POLICY_EXTRACT | 政策文件提取 |
| CASE_EXTRACT | 项目案例提取 |
| EXPERIENCE_EXTRACT | 操盘经验提取 |
| TOOL_EXTRACT | 实操工具提取 |
| DATA_EXTRACT | 数据资料提取 |

### V3 辅助类（8 个）

| 变量名 | 用途 |
|--------|------|
| PRE_ANALYSIS_PROMPT | 提取前预分析（质量评分 + 分类建议 + 结构识别 + source_nature） |
| QC_CHECK_PROMPT | 提取后批量质检（7 维度评分 + 举一反三可靠性，默认 15 条/批） |
| QC_CHECK_SINGLE_PROMPT | 逐条质检（F058 降级 L2 使用，简化 6 维度，1 条/次） |
| SEGMENT_SUMMARY_PROMPT | 文件结构摘要（分段建议） |
| CROSS_SEGMENT_CHECK_PROMPT | 跨段补漏检查 |
| POLICY_SCAN_PROMPT | 政策引用扫描 |
| DUPLICATE_JUDGE_PROMPT | 重复知识点关系判断（5 种） |
| EXPERIENCE_STRUCTURE_PROMPT | 经验速记 V3 结构化 |

### 工具类（3 个）

| 变量名 | 用途 |
|--------|------|
| FILE_RENAME_PROMPT | 文件智能重命名 |
| TAG_SUGGESTION_PROMPT | 标签建议 |
| ARCHITECTURE_SUGGESTION_PROMPT | 架构扩充建议 |

### F048 体检/打磨类（6 个，v2.3.0-part2.2 落地）

| 变量名 | 模型 | 调用位置 |
|--------|------|---------|
| HEALTH_DIAGNOSIS_PROMPT | V3 | `health_checker._diagnose_polish_candidate()` |
| HEALTH_POLISH_PROMPT | R1 | `health_checker._polish_with_r1()` |
| HEALTH_POLISH_VERIFY_PROMPT | V3 | `health_checker._verify_polish()` |
| HEALTH_POLISH_CONSERVATIVE_PROMPT | V3 | `health_checker._polish_conservative()` |
| HEALTH_ISLAND_JUDGE_PROMPT | V3 | `health_checker._judge_island()` |
| HEALTH_MONETIZE_REPORT_PROMPT | V3 | `health_checker._dim6_monetize_score()` |

### F062 端到端测试类（1 个，v2.3.0-part3-alpha1 落地）

| 变量名 | 模型 | 调用位置 |
|--------|------|---------|
| E2E_RESPONSE_JUDGE_PROMPT | V3 | `e2e_tester._judge_single_event()` |

### F2 精品候选判定类（2 个,v2.3.1 落地）

| 变量名 | 模型 | 调用位置 | 视角侧重 |
|--------|------|---------|---------|
| PREMIUM_JUDGE_CLIENT_PROMPT | V3 | `premium_judge._judge_one_kp(view='client')` | 实用性优先(老唐跟客户讲判断/经验时拿得出手) |
| PREMIUM_JUDGE_RFP_PROMPT | V3 | `premium_judge._judge_one_kp(view='rfp')` | 权威性优先(投标文件需文号/级别/数据可追溯) |

**输入占位符**(两条 Prompt 一致):`{filename}` / `{category_path}` / `{source_authority}` / `{qa_score}` / `{has_annotation}` / `{kp_content_json}`(精简至 3000 字内,防 token 爆炸)

**输出结构契约**(两条一致):
```json
{
  "recommendation": "strong" | "optional" | "not",
  "reason": "<200 字以内一句话理由>",
  "score": 0-100
}
```

**设计决策**(Phase 2 冻结):两条独立 Prompt,**不合并一次调用**。同一条 kp 允许 `client=strong + rfp=not`(视角分化),AI 调用次数 = kp 数 × 2。强推门槛不在 AI 侧实现,由前端按 `composite_score` Top 10-15% 标 strong,中段 40% 标 optional,低 45% 不返回。

### F055 本地问答助手类(3 个,v2.3.2 落地)

| 变量名 | 模型 | 调用位置 | 用途 |
|--------|------|---------|------|
| QA_RETRIEVAL_RANK_PROMPT | V3 | `qa_assistant._rerank_with_v3()` | 检索候选 ≥6 条时二次重排,Top 5 喂生成(<6 跳过省钱) |
| QA_ANSWER_GEN_PROMPT | V3 主 / R1 备 | `qa_assistant._generate_4_panels()` | 4 板块通用回答主生成,L2 R1 兜底用 deepseek-reasoner 走同 Prompt |
| QA_FOLLOWUP_GEN_PROMPT | V3 | `qa_assistant._generate_followups()` | 主链 followup_questions 为空时备用补救调用 |

**输入占位符**:
- `QA_RETRIEVAL_RANK_PROMPT`: `{user_query}` / `{candidate_count}` / `{candidates_json}`(候选 KP 摘要 ≤10 条)
- `QA_ANSWER_GEN_PROMPT`: `{user_query}` / `{kp_count}` / `{retrieved_kps_json}`(Top 5 完整字段含 description/practical_insights/excerpt)
- `QA_FOLLOWUP_GEN_PROMPT`: `{user_query}` / `{used_kp_titles}`(已引用) / `{nearby_kp_titles}`(周边相关 ≤8)

**输出结构契约**:
```json
// QA_RETRIEVAL_RANK_PROMPT
{ "ranked_kp_ids": [101, 102, ...], "reasoning": "<排序理由>" }

// QA_ANSWER_GEN_PROMPT(4 板块通用)
{
  "direct_answer": "<200-400 字直答>",
  "evidence_kp_ids": [101, 102, 103],     // 严格子集校验
  "followup_questions": [{"q": "...", "reason": "..."}],
  "coverage_gap": "<诚信兜底,主动暴露知识缺口,可空字符串表示覆盖完整>"
}

// QA_FOLLOWUP_GEN_PROMPT
{ "followups": [{"q": "...", "reason": "..."}] }
```

**关键约束**:
- `evidence_kp_ids` **强制子集校验**(防 V3 编造):由 `qa_assistant._generate_4_panels` 在解析后过滤,只保留 retrieved_kps 集合内的 ID;若全编造则兜底为前 3 条
- `direct_answer` 长度软约束 200-400 字(Prompt 指导,不强制截断)
- `coverage_gap` **诚信兜底设计**:Prompt 明确要求"如果库内信息不足以充分回答,主动说明缺什么";空字符串视为"覆盖完整",前端渲染为绿色"本次回答覆盖完整"
- L2 R1 兜底**复用同一 Prompt**(`QA_ANSWER_GEN_PROMPT`),仅 `model_override='deepseek-reasoner'` 切换,无需独立 Prompt
- `is_test_query=1` 与 Prompt 无关(模型不知道这是测试,Prompt 不变)

**设计决策**(Phase 2 冻结):
- 4 板块**单次调用**生成,不拆 4 次(成本 ÷4 + 上下文一致性)
- 朋友试用模式 `mode='friend'` **不影响 Prompt**(同一套 Prompt,只在前端隐藏元数据);Prompt 不知道是朋友还是老唐,这是设计目标(避免"对朋友说一套对自己说一套")
- `practical_insights` 喂入 Prompt(老唐 20 年实战的差异化资产),不只是 description

### 待激活（3 个）

| 变量名 | 激活时机 |
|--------|---------|
| CONFLICT_DETECTION_PROMPT | v2.3.3 F020(原 v2.3.1 scope,延后) |
| VERSION_DIFF_PROMPT | 待定 |
| QA_DERIVATION_PROMPT | v3.1.0 F013 |

---

## 二、共享策略块

注入提取 Prompt 和 F048/F062 Prompt 的横切策略：

| 策略块 | 作用 | F048 | F062 |
|--------|------|------|------|
| PRODUCT_CONTEXT | 产品目标上下文 | HEALTH_POLISH / MONETIZE_REPORT | 不注入 |
| EXCERPT_REQUIREMENT | 原文摘录要求 | HEALTH_POLISH | 不注入 |
| DATA_PRECISION_RULE | 数据精确度强制（6 类数字） | HEALTH_POLISH / POLISH_CONSERVATIVE | 不注入 |
| SICHUAN_SENSITIVITY | 四川地域敏感标注 | HEALTH_POLISH | 不注入 |
| SELF_CHECK_INSTRUCTION | 自包含检验指令（6 条自检） | 不注入 | 不注入 |
| CONTEXT_RELAY_TEMPLATE | 分段上下文接力模板 | 不注入 | 不注入 |
| PRACTICAL_INSIGHTS_INSTRUCTION | 举一反三实操启示推导 | 不注入 | 不注入 |
| COMMON_TAG_OUTPUT_DESC | 三层标签+元数据输出描述 | 不注入 | 不注入 |
| DOCUMENT_FORM_INSTRUCTION | 文档形态识别与颗粒度适配 | 不注入 | 不注入 |
| SOURCE_NATURE_INSTRUCTION | 来源属性→分类策略映射 | 不注入 | 不注入 |

**关键区分**：
- **内省型 Prompt**（诊断 / 校验 / 孤岛精判 / E2E 语义判断）→ 不注入任何策略块
- **生产型 Prompt**（打磨 / 变现报告）→ 注入对应生产规则块

---

## 三、F048 6 个 Prompt 接口契约

### HEALTH_DIAGNOSIS_PROMPT（V3，诊断低分病根）

**输入占位符**：`{filename}` / `{knowledge_point_json}`
**策略块注入**：无
**输出**：单个 JSON 对象
```json
{
  "diagnosis": "病根描述 50-150 字",
  "root_cause_type": "hallucination | over_abstract | missing_data | weak_insight | structural_flaw | noise | other",
  "polish_direction": "improve | enrich | split | merge | drop",
  "polish_difficulty": "easy | medium | hard | impossible",
  "recommend_manual_review": true 或 false
}
```
**降级触发**：`recommend_manual_review=true` 或 `polish_difficulty=impossible` → L3；`polish_direction=drop` → 生成"建议删除"类型 suggestion
**硬约束**：diagnosis 具体指出"哪里不对"，禁空泛评语；不自己改写知识点；root_cause_type 选最主要一个病根不同时选多个

### HEALTH_POLISH_PROMPT（R1，创造性打磨）

**输入占位符**：`{filename}` / `{knowledge_point_json}` / `{diagnosis}` / `{polish_direction}`
**策略块注入**：PRODUCT_CONTEXT + DATA_PRECISION_RULE + SICHUAN_SENSITIVITY + EXCERPT_REQUIREMENT
**输出**：JSON 数组（split 可能多条，其他单条）
```json
[{
  "title": "打磨后标题 ≤30 字",
  "description": "打磨后正文 150-500 字",
  "practical_insights": [{"insight":"...", "basis":"...", "confidence":"high|medium|low"}],
  "tags": {"layer1":[...], "layer2":{...}, "layer3":[...]},
  "polish_notes": "本次打磨改了什么 ≤100 字"
}]
```
**R1 约束**：分段 ≤ 3000 字（超长截断 description 到 2000 字）；不设 max_tokens，不传 temperature；截断/格式异常**直接降级 L2**，不启用 F057 补救
**6 条硬约束**：禁止幻觉 / 禁止偏题 / 数据一致（数值必须保留）/ 分段克制 / 启示有据 / polish_notes 必填不能套话

### HEALTH_POLISH_VERIFY_PROMPT（V3，校验 R1 结果）

**输入占位符**：`{diagnosis}` / `{original_json}` / `{polished_json}`
**策略块注入**：无
**输出**：
```json
{
  "verify_pass": true 或 false,
  "fail_reasons": ["幻觉|偏题|数据篡改|过度发挥|事实错误|格式异常"],
  "re_score": 1-5 整数,
  "confidence": "high | medium | low"
}
```
**降级触发**：`verify_pass=false` / `re_score<原 qa_score` / `confidence=low` → L2
**fail_reasons 6 种固定取值**：幻觉 / 偏题 / 数据篡改 / 过度发挥 / 事实错误 / 格式异常

### HEALTH_POLISH_CONSERVATIVE_PROMPT（V3，L2 保守打磨）

**输入占位符**：`{diagnosis}` / `{original_json}`
**策略块注入**：DATA_PRECISION_RULE（仅提醒保留原数值）
**输出**：同 HEALTH_POLISH 单条结构，`polish_notes` 必须以"仅保守微调"开头
**禁止清单**：❌ 新增数据/案例 / ❌ 扩写发挥推理 / ❌ 改变结论立场 / ❌ 把"三句话"扩成"五句话"（信息密度不变）
**允许清单**：✅ 修语病/错别字 / ✅ 补齐漏标签 / ✅ 精简冗余 / ✅ 修 JSON 格式 / ✅ 整理 insights 列表
**无法修补场景**：`polish_notes="仅保守微调: 无实质性可修补空间,建议人工介入"` → 走 L3

### HEALTH_ISLAND_JUDGE_PROMPT（V3，孤岛精判）

**输入占位符**：`{knowledge_point_json}`（精简 payload）/ `{nearby_kp_summary}`（最多 8 条，格式 `- [分类/子分类] 标题`）
**策略块注入**：无
**输出**：
```json
{
  "is_island": true 或 false,
  "island_type": "true_island | niche_topic | duplicate_candidate | structural_isolated | none",
  "relation_suggestion": "建议关联到哪类知识点 20-50 字"
}
```
**5 种 island_type 意义**：
- `true_island` 真孤岛 → **计入孤岛率**
- `niche_topic` 稀缺专题（独家经验有独立价值）→ **不计入**（关键设计：避免独家经验被误判）
- `duplicate_candidate` 重复嫌疑 → **不计入**
- `structural_isolated` 结构孤立（分类/标签打歪）→ **计入孤岛率**
- `none` 非孤岛 → **不计入**

**health_checker 判定**：`is_island=true` ⟺ `island_type ∈ {true_island, structural_isolated}`

### HEALTH_MONETIZE_REPORT_PROMPT（V3，变现匹配度报告）

**输入占位符**：`{library_summary_json}`（含 total_kp / high_quality_count / category_distribution / authority / monetize_tier / qa_score / tag_distribution A/C/D）
**策略块注入**：PRODUCT_CONTEXT（5 场景需与产品目标对齐）
**输出**：
```json
{
  "overall_monetize_score": 0-100,
  "scenario_scores": {
    "咨询答疑": {"score":..., "coverage":"好/中/差", "gap":"..."},
    "方案撰写": {...}, "政策解读": {...}, "汇报话术": {...}, "投标辅助": {...}
  },
  "feed_direction": ["方向1具体可执行", "方向2", "方向3"],
  "monetize_readiness": "ready | near_ready | need_work | not_ready"
}
```
**overall_monetize_score 加权**：咨询 25% + 方案 25% + 政策 20% + 汇报 10% + 投标 20%
**monetize_readiness 4 档**：ready (≥80 / 5 场景均 ≥70 / 精品 ≥500) / near_ready (60-80 / 至少 3 场景 ≥65 / 精品 ≥300) / need_work (40-60) / not_ready (<40)
**feed_direction 好样例**："优先补充 1.1 全域土地综合整治政策 的省级官方文件（当前仅 3 条，且均无核心条款字段）" / 坏样例："补充政策类内容"

---

## 四、F062 E2E_RESPONSE_JUDGE_PROMPT 接口契约

### E2E_RESPONSE_JUDGE_PROMPT（V3，响应语义判断）

**定位**：对一次 HTTP 调用的响应 + 相关事件日志，判断是"真成功"还是"假绿色"（字面 200 但实际降级/抢救/吞异常）

**输入占位符**（6 个）：
- `{endpoint}` / `{method}` / `{status_code}`
- `{response_excerpt}` — 响应 body 前 2000 字
- `{recent_events_json}` — 最近 20 条相关 operation_events
- `{expected_behavior}` — 测试契约自然语言（默认"本次应一次成功，不应出现抢救/降级"）

**策略块注入**：无（内省型）

**输出**：
```json
{
  "judgment": "pass | warn | fail",
  "reasons": ["具体依据 50 字内"],
  "keywords_hit": ["抢救|降级|跳过|异常继续|假绿色"],
  "confidence": "high | medium | low"
}
```

**3 档 judgment**：
- `pass` 真成功：状态码合预期 + 结构齐全 + events 无抢救/降级/跳过/异常继续
- `warn` 可工作但瑕疵：状态对但字段缺失 / 出现抢救或降级但最终结果对
- `fail` 真失败/假绿色：状态不符预期 / 响应含 error/traceback / events 里跳过或异常继续 / 响应 200 但维度分=0

**4 类关键词识别**：
1. **抢救**（rescue/recovery）— 如 F057 截断补救、分段重提。本身非 bug，但在"本次应一次成功"场景下出现说明质量下降
2. **降级**（fallback/downgrade）— 三级降级、规则兜底、L2 保守打磨、manual_review_needed 等。降级出现就 warn 起步
3. **跳过**（skip/ignore/bypass）— 关键校验被绕过、候选被过滤 0 条。直接 fail
4. **异常继续**（exception_swallowed/silent_degrade/None fallback）— try/except X=None、print 当错误处理、静默 return None。直接 fail

**6 条硬约束（写入 system_prompt）**：
- keywords_hit 必须有实际依据，禁臆造
- reasons 具体指向字段或事件，禁空泛
- 不解读 expected_behavior 之外的业务语义
- confidence=low 时必须说明"信息不足"
- 字面 HTTP 200 + 背后降级 = warn 起步（除非降级链本身是期望行为如 F058 qc_downgrade）
- 不对产品逻辑做道德评价，只对"调用是否健康"做技术判断

**关键设计**：
- **不被字面 HTTP 200 蒙混**：响应 status=200、success=true，只要 events 里出现 warning/error 级抢救/降级/跳过/异常继续，无论响应多"漂亮"都必须判 warn 或 fail
- **事件日志是事实源**：recent_events_json 权重高于 response_excerpt 的"表面成功"
- **expected_behavior 是锚点**：同样走三级降级，对 F058 是预期（pass/warn），对"体检启动"是异常（fail）

---

## 五、降级链

### F058 三级降级链（v2.2.3 全链路已落地）

```
主: QC_CHECK_PROMPT 批量 15 条/批
 └ 格式异常 → L1: QC_CHECK_PROMPT 拆小批 3 条/批 × 最多 2 轮重试
 └ 仍失败 → L2: QC_CHECK_SINGLE_PROMPT 逐条 1 条/次
 └ 仍失败 → L3: 本地规则兜底（长度/字段/excerpt 存在性）
            qa_source='rule_fallback' + qa_score=3 + 前端黄色高亮
```

**触发路径**：
1. 提取时自动触发（`extractor._quality_check`）
2. F061 历史补跑手动触发（工具箱"质检补跑" → `_qc_rerun_core` → `ext._quality_check`）

**QC_CHECK_SINGLE_PROMPT 设计要点**：
- 输入单个知识点，prompt 体积小，V3 不易格式异常
- 6 维度评分（比批量版少"重复嫌疑"一维，逐条看不到同文件其他 kp）
- 输出单个 JSON（不用数组），字段与批量版单条 item 一致
- 占位符：`{filename}` + `{knowledge_point_json}`

### F048 三层打磨降级链（v2.3.0-part2.2 已落地）

详见 `01_工程手册.md` §八。核心：V3 诊断 → R1 打磨 → V3 校验 → L2 V3 保守打磨 → L3 规则兜底

---

## 六、调用位置对照表

| Prompt | 引擎层调用 | 界面层触发 |
|--------|-----------|-----------|
| HEALTH_DIAGNOSIS_PROMPT | `health_checker._diagnose_polish_candidate()` | `POST /api/tools/health/start` → dim5 逐条诊断 |
| HEALTH_POLISH_PROMPT | `health_checker._polish_with_r1()` | 同上，诊断后 R1 打磨；前端左右对比展示 |
| HEALTH_POLISH_VERIFY_PROMPT | `health_checker._verify_polish()` | R1 后 V3 校验；verify 结果仅作降级判断，不前端展示 |
| HEALTH_POLISH_CONSERVATIVE_PROMPT | `health_checker._polish_conservative()` | L2 降级；前端黄色 L2 徽章 |
| HEALTH_ISLAND_JUDGE_PROMPT | `health_checker._judge_island()` | 维度④ 关联密度精判，结果展示在报告 dim4 卡 |
| HEALTH_MONETIZE_REPORT_PROMPT | `health_checker._dim6_monetize_score()` | 维度⑥ 变现场景，结果展示在报告"变现场景行"5 项分数条 |
| E2E_RESPONSE_JUDGE_PROMPT | `e2e_tester._judge_single_event()` | `POST /api/tools/e2e/start` → 维度⑤ 最近事件或本次响应 V3 判断 |

**F048/F062 路由全部不调用 Prompt**：Prompt 调用完全由引擎层承担；路由只做任务启动 / 读 DB / 写 DB。

---

## 七、新增 Prompt 的检查清单

新增 Prompt 时对照：

- [ ] 双 key 严格：`system_prompt` / `user_prompt_template`（不用 `system` / `user`）
- [ ] 占位符命名清晰，`.format()` 时缺占位符会 KeyError，兜底用合理常量（不留 None/空字符串让 V3 困惑）
- [ ] 内省型 vs 生产型分流：内省型不注入策略块，生产型按场景注入
- [ ] 输出结构有明确 JSON 模板写入 system_prompt，硬约束条目化
- [ ] 在 `get_all_prompt_names()` 追加登记
- [ ] PROMPT_VERSION 升版（提醒：F044 版本重提取会识别老 kp 为"待升级"，无实际提取 Prompt 改动时老唐可忽略数字）
- [ ] 引擎层顶层裸 import（禁 try/except 静默降级）
- [ ] 调用位置更新到本手册 §六

---

## 九、发布 JSON 标准 F056(v2.3.1-hotfix1 起)

> F056 是本地知识库 → 云端服务库的**契约层**。本地 SQLite 是生产库(加工车间),云端 PG+Qdrant 是服务库(交付车间),两库不共享存储,通过 F056 标准 JSON 同步。
>
> 当前版本:`schema_version = "f056-v1.0"`(精简版,2026-04-25 hotfix1 冻结)。
>
> 实装位置:`scripts/premium_exporter.py`(`_build_json` + 末尾 `validate_publish_json`),立规则 55 第 2 次落地不开独立 validator 文件。

### 9.1 设计原则（第 1 轮已锁的 5 件事）

| # | 决定 | 一句话理由 |
|---|---|---|
| 1 | excerpt 限长 1200 字、按句号截断;data 类放宽 2000 字 | 客户端 markdown 表格识别在校验函数实现 |
| 2 | kp_id 命名 `kp-{本地 id}` 字符串前缀 | 简洁优先,多发布者场景留 v2.0 |
| 3 | practical_insights[].confidence 公开(high/medium/low) | "诚实"是护城河,low 标签反而强化用户信任 |
| 4 | annotations 全发(含 disagree/correction) | "敢说真话"是付费理由,Tab 1 审核环节是发布前闸门 |
| 5 | 8 维属性标签锁死白名单:本地灵活、发布严格双层 | 升 v1.1 软规则:30 天 + 20 条稳定使用 |

### 9.2 v1.0 schema 顶层结构(承重墙 6 字段 + KP 13 字段)

**顶层 6 字段**(全必填):
- `schema_version` const="f056-v1.0"
- `publish_id` `pub-{16hex}` 幂等 key(SHA256(os.urandom+timestamp) 前 16 位)
- `published_at` ISO 8601 UTC(末尾 Z 后缀)
- `scope` enum 4 值(对齐 build_premium_export 的 scope 参数)
- `count` int(必须等于 len(items))
- `items` array

**KnowledgePoint 13 字段**(全必填):
`kp_id / title / content_type / category / excerpt / extracted_content / practical_insights / tags / quality / premium / source / annotations / timestamps`

**关键字段语义**(代码读不出的契约):
- `quality.authority` ← `knowledge_points.source_authority`(立规则 9 第 5 次应验:这是 schema 真名)
- `quality.access_level` 与 `premium.client/rfp` **正交**(01 工程手册 §5.7):前者付费墙,后者精品池视角
- `source.document_id` v1.0 承重墙,B 端投标 + C 端学生/自学者 三类客户必需(法律闭环第 4 项)
- `premium.freshness_status` 法律闭环字段:政策保鲜失效靠此字段 + 客户端徽章 + 服务条款
- `annotations[]` **无 title 字段**(annotations 表 init_tables 真无 title;v2.3.1-hotfix1 已修 db_manager + premium_exporter 对齐,立规则 9 第 8 次应验)
- `extracted_content` v1.0 不锁内层结构(5 种 content_type 输出形态不同),校验只保证它是 object

**不在 schema 的字段**(F056 第 2 轮论证砍到 v1.1 路线图,见 §9.3):
- 顶层:`library_uuid` / `replace_strategy` / `publisher` / `usage_terms`(永不入) / `relations` / `scope_meta`
- 嵌套:`source.canonical_url` / `source.page_hint` / `tags.attributes` 8 维 enum 锁死

### 9.3 v1.1 路线图(9 个字段的启用条件)

| 字段 | v1.0 砍掉理由 | v1.1 启用条件 |
|---|---|---|
| `library_uuid` 顶层 | 单发布者无混乱 | 老唐换电脑 / 重置库 / 多发布者出现 |
| `replace_strategy` 顶层 | 默认全量覆盖 | 增量发布需求出现 |
| `publisher` 顶层 | 单发布者 | 多发布者扩展(朋友试用扩到写) |
| `usage_terms` 顶层 | **永不入** schema | v2.4.0 服务条款层解决 |
| `relations` 顶层数组 | F030 未上线 | v2.3.3 F030 知识关联网络上线 |
| `scope_meta` 顶层 object | by_category 使用率不足 | 真实使用 ≥3 次 |
| `source.canonical_url` | 无学术客户反馈 | C4/C5 学术客户真实反馈 |
| `source.page_hint` | 颗粒度够粗 | 老唐预处理顺便填 |
| `tags.attributes` enum 锁死 | v1.0 软规则期 | 30 天稳定 / 20 条稳定 / 出现攻击值 |

### 9.4 校验函数 `validate_publish_json`

**位置**:`scripts/premium_exporter.py` 末尾(立规则 55 第 2 次落地)
**签名**:`def validate_publish_json(json_str: str) -> Tuple[bool, List[str]]`
**职责**:结构 + 业务规则校验,不修复;不调 V3 不调 db
**错误码**:E001-E027 共 15+ 项(完整码表见代码;UI 按前缀高亮)
**降级策略**:E001-E013 阻断;E014(excerpt 超长)可由调用方选自动截断或拒发

| 错误码段 | 类别 | 阻断? |
|---|---|---|
| E001 / E002 | JSON 结构损坏 | 阻断 |
| E003 / E004 / E005 / E007 / E008 | 顶层契约违反 | 阻断 |
| E006 / E009 | 顶层一致性 | 阻断 |
| E010 / E011 / E012 / E013 | KP 基础契约 | 阻断 |
| E014 | excerpt 超长 | 可降级 |
| E020-E027 | KP 嵌套字段(category/quality/premium/source/tags/timestamps/annotations/insights) | 按规则严重度 |

### 9.5 法律闭环 4 类(F056 第 2 轮论证沉淀,不入 schema 但锚定责任)

| 风险 | 闭环手段 | 落地点 |
|---|---|---|
| 政策保鲜失效 | `premium.freshness_status` 字段 + 客户端徽章 + 服务条款 | schema(承重墙) |
| 注解点名批评 | Tab 1 审核闸门 + 二次确认 | review.html(本版未动) |
| 二次传播侵权 | v2.4.0 服务条款 + 数字水印 | **不入 schema** |
| 用户用错反咬 | `source.document_id` 字段 + 服务条款 | schema(承重墙) |

### 9.6 客户视角覆盖（8 类全覆盖）

- **B 端 3 类**:决策者 / 执行者 / 投标项目经理
- **C 端 5 类**:返乡青年 / 咨询助理 / 自媒体 / 学生 / 自学者

字段承重墙均按上述 8 类客户的最低必需集合反推。

### 9.7 v1.0 → v1.1 演进通用动作

(1) 修 `_build_kp_payload_v1_0` 加字段 → (2) 升 `schema_version` 到 `f056-v1.1` → (3) `validate_publish_json` 加新规则 → (4) 本手册 §9.2/9.3 同步 → (5) CHANGELOG 记 schema 演进条目
