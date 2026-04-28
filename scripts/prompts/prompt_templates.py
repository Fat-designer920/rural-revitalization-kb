"""
prompt_templates.py - Prompt模板库
路径：scripts/prompts/prompt_templates.py
版本：v2.3.4-hotfix1 - 多模型整段重提 PROMPT 100% 复用

变更说明（v2.3.4-hotfix1）：
  - PROMPT_VERSION 从 v2.3.4 升到 v2.3.4-hotfix1
  - Prompt 内容**完全不动**:同一套 prompt 同时喂 R1 / Kimi-K2.6(思考型) / R1 跨厂商镜像
  - 不为 Qwen3 / Kimi 单独适配:OpenAI 兼容格式 + JSON Lines 输出 + 思考型默认开启
  - extractor.py L1/L2 通过 chat_via_siliconflow 调用,prompt 包字面相同

变更说明（v2.3.0-part3-alpha1 对话 1/3）：
  - 新增 1 个 F062 体检 Prompt 正式版文本:
    * E2E_RESPONSE_JUDGE_PROMPT (V3, 端到端响应语义判断)
      职责: 对 HTTP 响应 + 最近 operation_events 片段做"真假绿色"判断
      核心: 识别"抢救/降级/跳过/异常继续"等关键词,揪出"字面 200 但实际降级"
      输出: judgment=pass/warn/fail + reasons + keywords_hit + confidence
  - 双 key 严格对齐对话 A 立规则:system_prompt / user_prompt_template
  - 顶层可 import（对话 2 e2e_tester.py 将顶层 from ... import E2E_RESPONSE_JUDGE_PROMPT,
    禁止 try/except + None 降级模式）
  - 内省型 Prompt,不注入策略块(对齐 F048 HEALTH_DIAGNOSIS 模式)
  - PROMPT_VERSION 从 v2.3.0-part2.2 升到 v2.3.0-part3-alpha1
  - get_all_prompt_names() 追加 1 条 F062 Prompt 登记

变更说明（v2.3.0-part2.2 对话A）：
  - 新增 6 个 F048 体检/打磨 Prompt 正式版文本(之前 v2.3.0-part2 仅在 03 手册声明契约,代码未落地):
    * HEALTH_DIAGNOSIS_PROMPT        (V3, 低分病根诊断)
    * HEALTH_POLISH_PROMPT           (R1, 创造性打磨)
    * HEALTH_POLISH_VERIFY_PROMPT    (V3, 打磨结果校验)
    * HEALTH_POLISH_CONSERVATIVE_PROMPT (V3, L2 保守打磨)
    * HEALTH_ISLAND_JUDGE_PROMPT     (V3, 孤岛精判)
    * HEALTH_MONETIZE_REPORT_PROMPT  (V3, 变现匹配度报告)
  - 每个 Prompt 按适配场景注入共享策略块:
    * HEALTH_POLISH_PROMPT 注入 PRODUCT_CONTEXT / DATA_PRECISION_RULE / SICHUAN_SENSITIVITY / EXCERPT_REQUIREMENT
    * HEALTH_POLISH_CONSERVATIVE_PROMPT 注入 DATA_PRECISION_RULE(严格禁止新增数据)
    * HEALTH_MONETIZE_REPORT_PROMPT 注入 PRODUCT_CONTEXT(5 种变现场景与产品目标对齐)
    * 诊断 / 校验 / 孤岛精判 三个内省型 Prompt 不注入策略块(职责是判断,不是生成)
  - PROMPT_VERSION 从 v2.2.3 升到 v2.3.0-part2.2(跨越 v2.3.0-part2 版号占位)
  - get_all_prompt_names() 追加 6 条 F048 Prompt 登记(总数 21 → 27)
  - 与 health_checker.py v2.3.0-part2-alpha2 import 契约完全对齐

变更说明（v2.2.3）：
  - 新增SOURCE_NATURE_INSTRUCTION共享策略块（来源属性→分类策略映射）
  - 注入全部5个提取Prompt，位于DOCUMENT_FORM_INSTRUCTION之后
  - PRE_ANALYSIS_PROMPT新增source_nature输出字段（6种来源类型）
  - CONTEXT_RELAY_TEMPLATE新增source_nature传递
  - DOCUMENT_FORM_INSTRUCTION系统性文章新增3条合并规则（总分合并/因果链不拆分/论点去重）
  - 解决：第三方调研报告被全部分成"操盘经验"、系统性文章知识点重叠过多
  - PROMPT_VERSION升级v2.2.3

变更说明（v2.2.2）：
  - 新增DOCUMENT_FORM_INSTRUCTION共享策略块（文档形态识别→颗粒度适配）
  - 注入全部5个提取Prompt，位于PRODUCT_CONTEXT之后、颗粒度标准之前
  - 解决：编制大纲被拆成十几条碎片、系统性分析文章论证链断裂等颗粒度失控问题
  - 四种文档形态：碎片记录(默认)/系统性文章/框架大纲/数据密集型

变更说明（v2.2.1）：
  - PROMPT_VERSION改为v2.2.1
  - EXCERPT_REQUIREMENT重写：去掉章节编号、禁止整段搬运、截取实质性内容
  - 政策类颗粒度标准新增反面定义（什么不算一个知识点）
  - 政策类输出结构字段注释重写：明确original_excerpt/core_provisions/implementation_points三者区别
  - 案例类/经验类输出结构字段注释同步强化
  - QC_CHECK_PROMPT新增第7维度"提炼增值度"，检查核心条款与原文是否重复

变更说明（v2.2.0 F045）：
  - 新增EXPERIENCE_STRUCTURE_PROMPT(V3模型，经验速记自动结构化)
  - 保留v2.1.1全部内容不变

变更说明（v2.1.1 F038）：
  - PROMPT_VERSION改为v2.1.1
  - 新增PRACTICAL_INSIGHTS_INSTRUCTION共享策略块
  - 5个提取Prompt输出结构新增practical_insights数组字段（含insight/basis/confidence）
  - QC_CHECK_PROMPT从5维度扩展到6维度（新增举一反三可靠性）
  - QC输出新增insight_reliability字段(reliable/uncertain/unreliable/no_insights)
  - 保留v2.1.0-d全部内容不变

变更说明（v2.1.0-c）：
  - 5个提取Prompt全部深度重写：注入产品目标上下文+颗粒度标准+正反示例+自检指令
  - 新增四川地域敏感标注要求
  - 新增数据精确度强制要求
  - 新增分段上下文接力模板（供extractor.py使用）
  - 新增PROMPT_VERSION常量（供版本追踪）
  - 新增4个V3辅助Prompt：预分析/质检/结构摘要/跨段补漏
  - 输出JSON结构不变，与现有extractor.py完全兼容

保留不变：
  - FILE_RENAME_PROMPT / TAG_SUGGESTION_PROMPT / QA_DERIVATION_PROMPT
  - 标签注入机制（_build_tag_reference / get_extraction_prompt）
  - 待激活占位Prompt（CONFLICT_DETECTION等）
"""

import sys
from pathlib import Path

# 确保能导入tag_config
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.tag_config import (
        get_layer1_for_prompt, get_layer2_for_prompt,
        LAYER3_KEYWORD_RULES, get_metadata_for_prompt
    )
except ImportError:
    from tag_config import (
        get_layer1_for_prompt, get_layer2_for_prompt,
        LAYER3_KEYWORD_RULES, get_metadata_for_prompt
    )


# ============================================================
# Prompt版本号（v2.1.0-c新增）
# extractor.py提取时记录此版本号到knowledge_points表
# ============================================================

PROMPT_VERSION = "v2.3.4-hotfix1"


def get_prompt_version():
    """返回当前Prompt版本号，供extractor.py调用"""
    return PROMPT_VERSION


# ============================================================
# 通用策略块（各Prompt共享）
# ============================================================

PRODUCT_CONTEXT = """
## 产品目标（你必须理解这些知识点将来做什么用）

你提取的每一条知识点，都是未来知识产品的"原材料"，而不是简单的信息摘录。

这些知识点将用于：
1. B端付费内容：操盘指南、政策解读专栏、投标方案参考、深度分析文章
2. C端问答助手：基层干部和项目经理的订阅制问答服务

目标读者是这三类人（他们愿意为好内容付费）：
- 工程咨询公司项目经理：需要投标方案的政策依据、案例举证、数据支撑
- 地方政府干部和村级组织：需要申报指导、合规操作、汇报材料的专业支撑
- 施工企业负责人：需要指标核算标准、验收要点、资料整理规范

因此，你提取的每条知识点必须满足"独立可用"标准：
- 读者只看这一条知识点，不看原文，就能准确理解并在工作中使用
- 一条知识点只讲一件事，不要把多个要点混在一起
- 必须包含足够的上下文，脱离原文不会产生歧义"""

EXCERPT_REQUIREMENT = """
## 原文摘录要求（极其重要）
original_excerpt字段是知识点最核心的原始素材，未来将用于辅助撰写文章、生成知识产品。必须遵守：
1. **截取实质性条款**：去掉章节编号（如"一、""二、""（一）""（二）""1.""2."）和段落引导语（如"目标任务""支持政策""工作要求""总体目标"等标题性文字），只保留实质性的条款语句
2. **只摘本知识点相关的内容**：如果原文一段话包含多个独立要点，只截取与本知识点直接相关的语句，不要把整段话全部复制
3. **保留完整语义**：摘录要语义完整（通常50-200字），让人脱离原文也能看懂
4. **原文精度**：数值、名称、表述必须与原文一致，不得改写或概括
5. **可直接引用**：这段摘录要达到"可以直接复制到文章中使用"的质量标准

原文摘录的反面示例（禁止出现）：
- 把"一、目标任务 以科学合理规划为前提，以乡镇为基本实施单元……"整段搬过来 → 应该去掉"一、目标任务"，只留实质条款
- 把包含3个独立规定的整段都复制 → 应该只截取与本知识点对应的那1条规定
- 摘录超过250字且包含多个独立信息 → 说明本知识点该拆分或摘录该精简"""

DATA_PRECISION_RULE = """
## 数据精确度（强制要求）
涉及以下内容时，必须原文精确摘录，禁止概括性描述：
- 金额（如"不低于3000万元"，不能写"资金规模较大"）
- 面积（如"实施面积不低于300亩"，不能写"面积较大"）
- 比例（如"不低于50%"，不能写"较高比例"）
- 期限（如"实施周期一般不超过3年"，不能写"周期较长"）
- 指标（如"新增耕地率不低于实施面积的5%"，不能写"有新增耕地要求"）
- 标准（如"亩均投资不超过3500元"，不能写"投资有上限"）
如果原文有模糊表述（如"适当""合理"），也要如实摘录原文的模糊表述，并在知识点中注明"原文未给出具体数值"。"""

SICHUAN_SENSITIVITY = """
## 四川地域敏感标注（重要）
当前知识库聚焦四川市场，提取时请特别标注：
1. 如果是四川省特有政策（如川西林盘、成德眉资同城化等），在知识点中明确标注"四川特有"
2. 如果是全国通用政策在四川的执行口径，标注"全国政策/四川执行"并说明四川的具体要求
3. 涉及具体区域时，尽量精确到市/县/镇（如"成都市崇州市桤泉镇"而非"四川某地"）
4. 如果不同市州执行标准有差异，分别提取并标注差异"""

SELF_CHECK_INSTRUCTION = """
## 自检指令（提取完成后必须执行）
对你提取的每一条知识点，逐条自检：
1. 独立可用性检验：如果一个从未看过原文的项目经理只看这一条知识点，他能否准确理解并在工作中使用？如果不能，补充必要的上下文。
2. 颗粒度检验：这一条知识点是否只讲了一件事？如果包含多个独立要点，必须拆分为多条。
3. 数据完整性检验：涉及数字的地方是否精确摘录了原文？有没有遗漏单位、年份、统计口径？
4. 标签一致性检验：打的标签和知识点内容是否匹配？不要出现内容讲资金但标签没选"资金筹措"的情况。
5. 字段增值性检验：核心条款/核心策略/核心结论是否比原文摘录有明显的提炼增值？如果只是原文换个说法，必须重写——提炼出本质规则、红线、或行动要点。
6. 文档形态适配检验：回顾你识别的文档形态——如果是系统性文章，检查是否有论证链被拆碎的知识点（拆碎的表现：两条知识点说的是同一个论点的不同侧面，合并后信息密度更高）；如果是框架文件，检查是否有本应合并的章节结构被逐章拆分。"""

DOCUMENT_FORM_INSTRUCTION = """
## 文档形态识别与颗粒度适配（优先于下方颗粒度标准，必须先执行）

在开始逐段提取前，先通读全文，识别文档的形态类型，并据此调整提取策略：

**形态A - 碎片记录**（会议纪要、备忘录、经验要点列表、工作笔记、条目式规定）
→ 按下方颗粒度标准逐条拆分（默认模式，不需要特殊处理）

**形态B - 系统性文章**（有"问题→根因→对策"或"论点→论据→结论"完整论证结构的分析报告、深度思考、行业研究）
→ 按核心论点/论证链提取，不按段落逐条拆碎
→ 一个完整的问题诊断（现象+根因+影响）= 一条知识点
→ 一套完整的对策建议（目标+措施+预期效果）= 一条知识点
→ 一个独立的深度洞察（反常识判断+论证依据）= 一条知识点
→ 关键原则：论证链是这类文章最大的价值，拆碎后每条都变成孤立的"正确的废话"
→ **合并规则（必须遵守）**：
  1. 总分合并：如果文章有"总述段"概括后跟分述段展开，只提取分述，不单独提取总述（总述信息已被分述覆盖，单独提取等于重复）
  2. 因果链不拆分：同一主题的"原因分析"和"对策建议"如果构成直接因果对应关系（问题A→对策A），合并为一条知识点，保留完整论证链
  3. 论点去重：如果两条知识点的核心结论相同，只是一条侧重"为什么"、一条侧重"怎么做"，合并保留更完整的那条

**形态C - 框架/大纲文件**（编制大纲、章节结构说明、模板框架、标准体系、评审要点清单）
→ 合并为1-3条整体性知识点，保留完整结构
→ 一个编制大纲的完整章节结构+各章要点 = 一条知识点（而非每章拆一条）
→ 一套评审标准的完整检查框架 = 一条知识点
→ 关键原则：框架文件的价值在于完整结构，拆成"第1章写什么、第2章写什么"就失去了整体指导意义

**形态D - 数据密集型**（统计表、对比表、参数表、测算模型）
→ 按数据组提取，关联数据放同一条知识点
→ 同一测算模型的多个参数 = 一条知识点（而非每个参数拆一条）

识别完形态后，在extraction_notes中注明你识别的文档形态（如"本文为系统性分析文章，按论证链提取"），然后按对应策略开始提取。
"""

SOURCE_NATURE_INSTRUCTION = """
## 文档来源属性与分类策略（v2.2.3新增，必须遵守）

文档的来源属性决定了分类方向。请根据预分析提供的source_nature（或你自行判断），选择正确的分类策略：

- **research_report**（第三方调研分析、行业研究、学术论文）：
  → 优先分到"案例库/失败与风险案例"（如果内容以问题诊断和风险分析为主）
  → 或分到"经验库/反常识洞察"（如果内容以深度洞察、行业判断为主）
  → 绝不能分到"操盘经验"，因为这不是作者本人的操盘记录
  → experience_type优先选insight（反常识洞察）或pitfall（踩坑记录），而非method/strategy

- **personal_experience**（作者本人的操盘记录、工作笔记、复盘总结）：
  → 分到"经验库"各子类（策略判断/操盘方法/踩坑记录/反常识洞察/沟通话术）
  → experience_type根据内容选择strategy/method/pitfall/insight/communication

- **official_policy**（政府发文、法规、通知、规范性文件）：
  → 分到"政策库"各子类

- **project_case**（具体项目的案例报告、实施方案、验收报告）：
  → 分到"案例库"各子类

- **tool_template**（模板、合同、清单等工具性文档）：
  → 分到"工具库"各子类

- **data_material**（数据表、统计资料、测算模型）：
  → 分到"数据库"各子类

如果上下文中有source_nature信息，以该信息为准；如果没有，请根据文档内容自行判断来源属性。
"""

PRACTICAL_INSIGHTS_INSTRUCTION = """
## 举一反三：实操启示推导（v2.1.1新增，重要）
在提取原文信息之外，请主动推导对一线操盘人员有价值的实操启示。

规则：
1. 每条知识点推导0-3条实操启示（没有合理推导依据时不要硬凑，输出空数组即可）
2. 每条启示必须标注推导依据（basis）和置信度（confidence）
3. 置信度分三档：
   - high：有原文明确支撑或行业共识支持
   - medium：基于合理推断但原文未直接说明
   - low：属于经验性判断，需要实战验证
4. 禁止无依据的臆测，宁可不输出也不要编造
5. 启示要面向实操：告诉操盘人员"所以你应该怎么做"或"要特别注意什么"
6. 启示不能和implementation_points/execution_points重复——启示是需要经验推断的延伸建议，执行要点是原文能直接推导出的操作指南

好的实操启示示例：
- insight: "申报全域整治项目时，优先选择拆旧潜力大的乡镇，而非建新需求大的"
  basis: "原文要求新增耕地率不低于5%，拆旧区面积越大越容易满足指标"
  confidence: "high"
- insight: "EPC合同中应提前约定变更累计上限不超过15%"
  basis: "多个案例显示未约定变更上限导致超概，15%为行业常见约定值"
  confidence: "medium"

差的实操启示（禁止出现）：
- "该政策对乡村振兴有重要意义" → 废话，不可操作
- "建议关注后续政策变化" → 空泛，人人都知道
- "项目策划和申报主体应定位在乡镇层面" → 这是原文直接说的执行要点，不算举一反三

在每个知识点JSON中新增字段：
"practical_insights": [
  {"insight": "实操启示内容（一句话说清楚）", "basis": "推导依据", "confidence": "high或medium或low"}
]
如果该知识点没有可推导的实操启示，输出空数组 []。"""

THREE_LAYER_TAG_STRATEGY = """
## 三层标签打标策略（必须严格遵守）

标签是知识检索和产品组装的核心入口。每条知识点必须输出三层标签：

### 第一层：分类标签（suggested_category_tags）
- 从下方提供的固定清单中选择3-6个标签名（只填标签名称，不填编号）
- A组（业务领域）和C组（知识形态）必选至少各1个
- E组（稀缺度）和F组（内容状态）必选各1个
- B组（项目阶段）和D组（客户视角）有关就选，无关不选
- 不要自创标签，必须严格从清单中选

### 第二层：属性标签（suggested_attribute_tags）
- 按下方列出的维度，从候选值中选择（只填与本知识点相关的维度，无关维度不填）
- 如果某个维度是"自由填写"，则填具体值（如区域填"成都市崇州市"，数据年份填"2024"）
- 输出为JSON对象，key是维度英文名，value是选中的值

### 第三层：关键词（suggested_keywords）
- 按下方关键词规则提取5-15个
- 必须覆盖：术语类、实体类、场景类三个角度
- 输出为字符串数组

### 元数据建议
- suggested_readiness：根据内容质量判断就绪度
- suggested_authority：根据内容来源判断权威度"""

# 三层标签的JSON输出字段说明（注入到每个Prompt的输出结构末尾）
COMMON_TAG_OUTPUT_DESC = """
"suggested_category_tags": ["从第一层清单选3-6个标签名称"],
"suggested_attribute_tags": {"维度英文名": "值", ...},
"suggested_keywords": ["关键词1", "关键词2", ...],
"suggested_readiness": "draft或quotable或premium",
"suggested_authority": "official或authoritative或firsthand或informal",
"practical_insights": [{"insight":"实操启示(一句话)","basis":"推导依据","confidence":"high或medium或low"}]
"""


# ============================================================
# 分段上下文接力模板（v2.1.0-c新增，供extractor.py使用）
# extractor.py在分段提取时，将此模板填充后附加到user_prompt前面
# ============================================================

CONTEXT_RELAY_TEMPLATE = """
=== 分段提取上下文（请仔细阅读） ===
本文件共{total_segments}段，当前是第{current_segment}段。

【文档来源属性】
{source_nature}

【文件整体结构摘要】
{file_structure_summary}

【前一段已提取的知识点标题】
{previous_titles}

【重要提示】
1. 不要重复提取上述已有的知识点
2. 如果本段内容引用了前文的定义或条件，请在知识点中补充必要上下文，确保独立可用
3. 如果本段出现"前述""上述""按照第X条规定"等引用，请查找上下文补全具体内容
"""


# ============================================================
# 文件重命名Prompt（不变）
# ============================================================

FILE_RENAME_PROMPT = {
    "system_prompt": """你是乡村振兴领域的资料管理专家。根据文件内容生成规范化文件名和分类标签。
文件命名规则：[年份][类型标记]_[核心主题]_[来源/地域]，类型标记：政策=ZC,案例=AL,经验=JY,工具=GJ,数据=SJ
输出JSON格式：
{"renamed_filename":"新文件名(不含扩展名)","content_type":"policy/case/experience/tool/data",
"domain_tags":["标签1","标签2"],"region_tag":"地域","policy_level":"国家级/省级/市级/区县级/非政策文件",
"brief_summary":"50字以内摘要"}""",
    "user_prompt_template": """分析以下文件,生成规范化文件名和标签。
原始文件名：{original_filename}
文件类型：{file_type}
内容摘要(前3000字)：
{content_preview}
请严格按JSON格式输出。"""
}


# ============================================================
# 标签建议Prompt（v2.0.0，不变）
# ============================================================

TAG_SUGGESTION_PROMPT = {
    "system_prompt": """你是乡村振兴领域的知识管理专家。为知识内容进行三层标签打标。
输出JSON格式：
{"suggested_category_tags": ["标签1","标签2",...],
 "suggested_attribute_tags": {"维度名":"值",...},
 "suggested_keywords": ["关键词1","关键词2",...],
 "primary_tag": "最核心的第一层标签名"}""",
    "user_prompt_template": """为以下内容进行三层标签打标。
标题：{title}
类型：{content_type}
摘要：{content_summary}
请严格按JSON格式输出。"""
}


# ============================================================
# 5个提取Prompt（v2.1.0-c 深度重写，v2.2.1 字段职责修正）
# 核心升级：产品导向+颗粒度标准+正反示例+自检+四川标注+数据精确
# v2.2.1升级：原文摘录精准化+核心条款与原文去重+执行要点操盘化
# 标签清单由get_extraction_prompt()动态注入
# ============================================================

_POLICY_EXTRACT_BASE = {
    "system_prompt": PRODUCT_CONTEXT + DOCUMENT_FORM_INSTRUCTION + SOURCE_NATURE_INSTRUCTION + """

你是乡村振兴政策分析专家，拥有20年土地政策实操经验。你的任务是从政策文件中萃取可直接用于付费产品的高质量知识点。

## 提取原则（必须严格遵守）
1. **全文通读**：从第一段到最后一段，逐段分析，不跳过任何章节、附则、附件说明
2. **细粒度提取**：每一个独立的政策要点、每一条具体规定、每一个数值标准、每一个时间节点，都单独提取为一个知识点。宁多勿少。
3. **不遗漏**：附则中的过渡条款、生效日期、例外规定同样要提取；表格中的数据逐行提取；脚注和备注中的限制条件也要捕获
4. **实操价值优先**：对于一线操盘人员有指导意义的条款重点提取
5. **保留原文精度**：涉及数值、比例、面积、金额的内容，必须精确引用原文表述，不得概括或四舍五入

## 政策类知识点的颗粒度标准
一个知识点 = 以下任意一个：
- 一个具体规定（如"节余指标可在省域范围内流转交易"）
- 一个适用条件（如"申报全域整治须满足：实施面积不低于XXX亩"）
- 一个数字指标（如"新增耕地率不低于实施面积的5%"）
- 一个时间节点（如"2024年6月30日前完成验收"）
- 一个禁止/限制事项（如"严禁以整治之名违规占用永久基本农田"）
- 一个资金使用规则（如"指标交易资金不低于50%用于拆旧区农民安置"）

以下情况说明颗粒度有问题，必须修正：
- 一整个章节的"目标任务"或"总体要求"段落作为一条知识点 → 太粗，应拆分为多个具体规定
- 把"实施单元""整治范围""整治目标"等不同规定混在同一条 → 每个独立规定单独提取
- 标题是"支持政策"或"工作要求"等章节标题 → 太笼统，应提取该段中每一条具体的政策规定
- 原文摘录超过200字且包含多个独立信息点 → 说明该拆分为多条知识点

## 好知识点 vs 差知识点（对照示例）

差知识点示例（禁止出现）：
- 标题"该政策对乡村振兴有重要意义" → 空泛，不可操作，读者看了等于没看
- 标题"资金管理要合规" → 废话，没有具体规定
- 标题"政策鼓励各地积极探索" → 太笼统，读者无法据此行动
- 摘要"该办法对实施面积有要求" → 缺失具体数字，不可引用

好知识点示例（这才是付费产品需要的质量）：
- 标题"全域整治单个乡镇最低实施面积300亩"
  摘要"四川省全域土地综合整治项目，单个乡镇实施面积不低于300亩，实施周期一般不超过3年（川自然资规〔2023〕5号第三条）"
- 标题"增减挂钩指标交易资金用途限制"
  摘要"增减挂钩节余指标交易资金中，不低于50%须用于被拆旧区农民安置补偿，地方政府不得挪用（川府办〔2018〕46号）"
- 标题"全域整治新增耕地率底线5%"
  摘要"全域土地综合整治项目竣工验收时，新增耕地面积不低于实施区域总面积的5%，其中旱改水面积可折算（自然资发〔2023〕95号第十二条）"

""" + EXCERPT_REQUIREMENT + DATA_PRECISION_RULE + SICHUAN_SENSITIVITY + THREE_LAYER_TAG_STRATEGY + """

## 每个知识点输出结构（注意三个核心字段的区别！）

**三个核心字段的职责区分（极其重要，必须严格遵守）：**
- original_excerpt = 原始素材：从原文截取的实质性条款语句，忠于原文不改写，去掉章节编号
- core_provisions = 规则提炼：用你自己的话提炼出这条规定的本质规则、红线或核心数字，比原文更精炼更抽象，绝不能是原文的改写或复述
- implementation_points = 操盘翻译：站在一线操盘人员角度，回答"这条规定对我的项目意味着什么？我该怎么做？有什么坑要避？"，不能复述原文

如果你发现core_provisions写出来和original_excerpt意思差不多只是换了说法，说明你没有真正提炼，必须重写。

{"title":"20字以内精确标题（必须包含核心数字或关键动词，禁止空泛表述）",
"original_excerpt":"原文实质性条款语句（50-200字，去掉章节编号和引导语，忠于原文不改写）",
"policy_name":"政策全称",
"issuing_body":"发布机构",
"policy_level":"国家级/省级/市级/区县级",
"issue_date":"发布日期",
"core_provisions":"核心规则提炼（不是原文改写！提炼出本质规则/红线/数字，比原文更精炼，100字内）",
"applicable_scope":"适用范围（地域+对象）",
"key_dates":"关键时间节点（生效日、截止日、过渡期等）",
"implementation_points":"操盘执行要点（这条规定对操盘人员意味着什么？该怎么做？有什么坑？不要复述原文）",
"parent_policy":"上位政策依据",
"diff_from_previous":"与旧版或相关政策的差异（如有）",
"source_page":"页码或章节号",
"source_keyword":"定位关键词",
"suggested_category_code":"分类编码如1.1",
""" + COMMON_TAG_OUTPUT_DESC + """}

## 输出格式（v2.3.4 升级:JSON Lines）
逐行输出,每条知识点单独一行,行间用换行符分隔。每行必须是一个独立完整的 JSON 对象。
最后一行(可选)输出元数据对象:{"_meta":true,"file_summary":"100字文件概述","extraction_notes":"提取过程说明"}

正确示例(每行一个独立 JSON,行间换行,无数组语法):
{"title":"...","original_excerpt":"...",...其他字段}
{"title":"...","original_excerpt":"...",...其他字段}
{"_meta":true,"file_summary":"...","extraction_notes":"..."}

禁止输出:
× {"knowledge_points":[...]} 数组结构
× ```json ... ``` 代码块包装
× 任何解释文字

## 特别注意
- 一个政策文件通常应提取5-30个知识点
- 表格内容要拆分为独立知识点
- "鼓励""支持""禁止"等不同力度的表述要区分提取
""" + PRACTICAL_INSIGHTS_INSTRUCTION + SELF_CHECK_INSTRUCTION,

    "user_prompt_template": """请对以下政策文件进行全文逐段分析，萃取所有可用于付费产品的高质量知识点。

要求：
1. 每条知识点必须"独立可用"——读者只看这一条就能理解并使用
2. 涉及数字必须精确摘录原文，禁止概括
3. 标注四川特有 vs 全国通用
4. 原文摘录去掉章节编号，只截取实质性条款语句
5. 核心条款必须是提炼，不能是原文换个说法
6. 执行要点要站在操盘者角度写，回答"对我意味着什么"

文件名：{filename}
可用分类：1.1全域土地综合整治政策 1.2增减挂钩与占补平衡 1.3集体经营性建设用地入市 1.4专项债与资金政策 1.5川西林盘保护政策 1.6乡村振兴综合政策 1.7自然资源与规划政策

{tag_reference}

全文内容：
{full_content}

请逐段通读上述全文，提取每一个有实操价值的知识点，按 JSON Lines 格式输出(每行一个独立完整 JSON 对象，最后一行可选输出 _meta 元数据)。"""
}

_CASE_EXTRACT_BASE = {
    "system_prompt": PRODUCT_CONTEXT + DOCUMENT_FORM_INSTRUCTION + SOURCE_NATURE_INSTRUCTION + """

你是乡村振兴项目咨询顾问，拥有丰富的项目操盘经验。你的任务是从案例材料中萃取可直接用于付费产品的高质量知识点。

## 提取原则（必须严格遵守）
1. **全文通读**：从项目背景到最终成效，逐段分析，不跳过任何细节
2. **细粒度提取**：项目的每个关键环节都要独立提取知识点。一个案例通常应提取5-20个知识点
3. **量化数据必保留**：所有涉及面积、金额、比例、时间、收益率的数据必须精确提取
4. **资金结构是重中之重**：资金来源、资金比例、融资方式、还款安排等必须详细拆分提取
5. **成功因素和风险因素都要提**
6. **可复制性分析**：每个知识点都要分析其适用条件和可复制的边界

## 案例类知识点的颗粒度标准
一个知识点 = 以下任意一个：
- 一个可复用的做法（如"EPC+O打捆招标降低管理成本"）
- 一个关键决策及其依据（如"选择先做拆旧再做建新，因为XX原因"）
- 一个具体成效数据（如"节余指标1200亩，交易收入2.4亿元"）
- 一个资金来源或拼盘方式（如"专项债8000万+财政整合3000万+社会资本2000万"）
- 一个创新机制或模式（如"村民以宅基地入股，按面积折算股份"）
- 一个失败教训或风险点（如"因未做好群众工作导致拆迁停滞6个月"）

以下情况说明颗粒度有问题，必须修正：
- 把项目背景、做法、成效混在同一条 → 应拆分为独立知识点
- 原文摘录超过200字且包含多个独立信息点 → 应拆分

## 好知识点 vs 差知识点（对照示例）

差知识点示例（禁止出现）：
- 标题"项目取得了良好的社会效益" → 空泛，没有数据
- 标题"资金管理规范" → 废话，没说怎么管的
- 标题"该项目具有推广意义" → 套话，读者无法参考
- 摘要"通过多种渠道筹集资金" → 缺失具体渠道和金额

好知识点示例（这才是付费产品需要的质量）：
- 标题"崇州桤泉镇3.2亿全域整治资金拼盘结构"
  摘要"崇州市桤泉镇全域土地综合整治项目总投资3.2亿元，其中：专项债1.5亿元（占46.9%）、财政整合资金8000万元（占25%）、平台公司自筹6000万元（占18.7%）、社会资本参与3000万元（占9.4%）。专项债还款来源为增减挂钩指标交易收益。"
- 标题"村民宅基地入股分红机制设计"
  摘要"XX项目采用宅基地使用权入股方式，退出宅基地的农户按每亩折合2股计算，前5年保底分红每股800元/年，第6年起按实际经营收益分配，保底不低于500元/股。村集体持股30%用于公共设施维护。"

""" + EXCERPT_REQUIREMENT + DATA_PRECISION_RULE + SICHUAN_SENSITIVITY + THREE_LAYER_TAG_STRATEGY + """

## 每个知识点输出结构

**核心字段职责区分：**
- original_excerpt = 原始素材：忠于原文的案例描述，去掉章节编号
- core_strategy = 做法提炼：提炼出可复用的策略/模式/方法（比原文更抽象、更有迁移价值），绝不能是原文的改写
- implementation_results = 成效数据：用具体数字说明结果

{"title":"20字内精确标题（必须包含项目名或核心数据，禁止空泛表述）",
"original_excerpt":"原文实质性内容（50-200字，去掉章节编号，忠于原文不改写）",
"project_name":"项目全称",
"location":"省市县（尽可能精确）",
"scale":"项目规模（面积/投资额/涉及村庄数等）",
"background":"项目背景与启动原因（150字内）",
"core_strategy":"核心策略提炼（不是原文改写！提炼出可复用的做法/模式，200字内）",
"funding_sources":"资金来源与结构（详细列出每笔资金来源和金额比例）",
"implementation_results":"实施成效（用具体数据说明）",
"innovation_points":"创新点或亮点",
"applicable_conditions":"适用条件（什么情况下可以复制这个做法）",
"risk_warnings":"风险提示或注意事项",
"source_page":"页码或章节号",
"source_keyword":"定位关键词",
"suggested_category_code":"如2.1",
""" + COMMON_TAG_OUTPUT_DESC + """}

## 输出格式（v2.3.4 升级:JSON Lines）
逐行输出,每条知识点单独一行,行间用换行符分隔。每行必须是一个独立完整的 JSON 对象。
最后一行(可选)输出元数据对象:{"_meta":true,"file_summary":"100字概述","extraction_notes":"提取说明"}

正确示例:
{"title":"...","original_excerpt":"...",...其他字段}
{"title":"...","original_excerpt":"...",...其他字段}
{"_meta":true,"file_summary":"...","extraction_notes":"..."}

禁止输出 {"knowledge_points":[...]} 数组结构、```代码块、解释文字。

## 特别注意
- 资金数据是案例的灵魂
- 时间线上的关键节点要单独作为知识点
- 多个子项目或阶段要独立提取
""" + PRACTICAL_INSIGHTS_INSTRUCTION + SELF_CHECK_INSTRUCTION,

    "user_prompt_template": """请对以下案例材料进行全文逐段分析，萃取所有可用于付费产品的高质量知识点。

要求：
1. 每条知识点必须"独立可用"——读者只看这一条就能理解并参考
2. 资金数据必须详细拆分，精确到每一笔来源和金额
3. 标注四川特有 vs 全国通用
4. 原文摘录去掉章节编号，只截取实质性内容
5. 核心策略必须是提炼出的可复用做法，不能是原文换个说法

文件名：{filename}
可用分类：2.1全域土地综合整治项目 2.2增减挂钩项目 2.3川西林盘修复运营项目 2.4资金整合与融资创新案例 2.5乡村产业与运营案例 2.6失败与风险案例

{tag_reference}

全文内容：
{full_content}

请逐段通读上述全文，提取每一个有参考价值的知识点，保留所有量化数据，按 JSON Lines 格式输出(每行一个独立完整 JSON 对象，最后一行可选输出 _meta 元数据)。"""
}

_EXPERIENCE_EXTRACT_BASE = {
    "system_prompt": PRODUCT_CONTEXT + DOCUMENT_FORM_INSTRUCTION + SOURCE_NATURE_INSTRUCTION + """

你是知识管理顾问，擅长从实战经验中萃取可复用的操盘智慧。你的任务是从经验材料中萃取可直接用于付费产品的高质量知识点。

## 提取原则（必须严格遵守）
1. **全文通读**：逐段分析，从每一句话中寻找可提炼的实操智慧
2. **细粒度提取**：一段经验描述中可能包含多个独立的判断/方法/教训，必须拆分为独立知识点
3. **反常识洞察优先**：与行业常规认知不同但经实战验证的判断，是最高价值的知识点
4. **三分法则**：策略判断、操盘方法、踩坑教训三类要分别提取
5. **决策背景必须保留**
6. **验证状态要标注**

## 经验类知识点的颗粒度标准
一个知识点 = 以下任意一个：
- 一个判断依据（如"选择乡镇时优先看拆旧潜力而非建新需求"）
- 一个操盘方法（如"先做群众工作再签协议，不要边签边做"）
- 一个踩坑教训（如"EPC合同未约定变更上限，导致超概30%"）
- 一个反常识洞察（如"指标价格谈判中，主动报低价反而更容易成交"）
- 一个沟通话术（如"向分管副县长汇报时，重点讲收益而非风险"）
- 一个时机判断（如"政策窗口期通常在两会后3个月内，错过要等一年"）

以下情况说明颗粒度有问题，必须修正：
- 把多个独立经验混在同一条 → 拆分
- 原文摘录超过200字且包含多个独立判断 → 拆分

## 好知识点 vs 差知识点（对照示例）

差知识点示例（禁止出现）：
- 标题"群众工作很重要" → 正确的废话，人人都知道
- 标题"要做好前期准备" → 太笼统，没有具体指什么
- 标题"项目管理要规范" → 套话，毫无实操指导价值
- 摘要"与相关部门保持良好沟通" → 没说和谁沟通、沟通什么、怎么沟通

好知识点示例（这才是付费产品需要的质量）：
- 标题"拆旧时机选择：秋收后春节前是黄金窗口"
  摘要"实操经验表明，农房拆除的最佳时间窗口是秋收结束后到春节前（约10月-12月）。原因：(1)农忙结束农户有时间处理搬迁事宜；(2)年底前完成可纳入当年指标考核；(3)春节前农户有建房或购房的紧迫感，配合度最高。反例：春节后启动拆旧，农户外出务工导致联系困难，某项目因此延误4个月。"
- 标题"EPC合同必须约定变更上限15%"
  摘要"踩坑教训：某全域整治项目EPC合同未约定设计变更上限，施工方通过大量变更将合同金额从8000万推高到1.04亿元，超概30%。此后所有项目均在合同中加入条款：设计变更累计金额不得超过合同总价的15%，超出部分需重新报批。"

""" + EXCERPT_REQUIREMENT + DATA_PRECISION_RULE + SICHUAN_SENSITIVITY + THREE_LAYER_TAG_STRATEGY + """

## 每个知识点输出结构

**核心字段职责区分：**
- original_excerpt = 原始素材：忠于原文的经验描述，去掉章节编号
- core_conclusion = 结论提炼：一句话概括这条经验的核心判断（比原文更精炼），绝不能是原文的改写
- detailed_method = 操盘方法：具体怎么做、步骤是什么（不能复述原文，要翻译成操作指南）

{"title":"20字内精确标题（必须包含核心判断或方法，禁止空泛表述）",
"original_excerpt":"原文实质性内容（50-200字，去掉章节编号，忠于原文不改写）",
"experience_type":"strategy/method/pitfall/insight/communication",
"applicable_scenario":"适用场景描述（100字内，越具体越好）",
"core_conclusion":"核心结论提炼（一句话，不是原文改写！）",
"detailed_method":"具体做法或步骤（操作指南化，不复述原文）",
"supporting_evidence":"支撑依据",
"counterintuitive_level":"高/中/低/无",
"field_verified":"已验证/部分验证/待验证",
"context_dependencies":"背景依赖",
"common_mistakes":"常见误区",
"source_page":"页码或章节号",
"source_keyword":"定位关键词",
"suggested_category_code":"如3.1",
""" + COMMON_TAG_OUTPUT_DESC + """}

## 输出格式（v2.3.4 升级:JSON Lines）
逐行输出,每条知识点单独一行,行间用换行符分隔。每行必须是一个独立完整的 JSON 对象。
最后一行(可选)输出元数据对象:{"_meta":true,"file_summary":"100字概述","extraction_notes":"提取说明"}

正确示例:
{"title":"...","original_excerpt":"...",...其他字段}
{"title":"...","original_excerpt":"...",...其他字段}
{"_meta":true,"file_summary":"...","extraction_notes":"..."}

禁止输出 {"knowledge_points":[...]} 数组结构、```代码块、解释文字。

## 特别注意
- 经验材料中往往有大量隐性知识，要主动挖掘
- 沟通话术、汇报技巧等软性经验同样重要
- "差点出事"的经历和"最终没做"的决策同样有提取价值
""" + PRACTICAL_INSIGHTS_INSTRUCTION + SELF_CHECK_INSTRUCTION,

    "user_prompt_template": """请对以下经验材料进行全文逐段分析，萃取所有可用于付费产品的实操智慧。

要求：
1. 每条知识点必须"独立可用"——读者只看这一条就能理解并在实操中应用
2. 反常识洞察和踩坑教训优先提取（这是最有付费价值的内容）
3. 标注四川特有经验 vs 全国通用经验
4. 原文摘录去掉章节编号，只截取实质性内容
5. 核心结论必须是提炼，不能是原文换个说法

文件名：{filename}
可用分类：3.1策略判断类 3.2操盘方法类 3.3反常识洞察 3.4踩坑记录 3.5客户沟通与汇报经验

{tag_reference}

全文内容：
{full_content}

请逐段通读上述全文，提取每一条有复用价值的经验知识点，按 JSON Lines 格式输出(每行一个独立完整 JSON 对象，最后一行可选输出 _meta 元数据)。"""
}

_TOOL_EXTRACT_BASE = {
    "system_prompt": PRODUCT_CONTEXT + DOCUMENT_FORM_INSTRUCTION + SOURCE_NATURE_INSTRUCTION + """

你是实操工具整理专家。你的任务是从模板/工具文件中萃取可直接用于付费产品的结构化知识点。

## 提取原则（必须严格遵守）
1. **全文通读**：逐段逐节分析，包括模板正文、填写说明、注意事项、附件
2. **细粒度提取**：模板的每个核心章节、每个关键条款、每个填写要点都独立提取
3. **适用场景要明确**
4. **核心结构要完整**
5. **使用注意事项要全**

## 工具类知识点的颗粒度标准
一个知识点 = 以下任意一个：
- 一个模板的核心结构（如"可研报告的12章标准结构"）
- 一个关键条款要素（如"EPC合同中必须包含的5个风险转移条款"）
- 一个填写规范或注意事项（如"投资估算表中不可预见费取比不得超过10%"）
- 一个审查要点（如"评审专家重点关注的3个数据一致性问题"）
- 一个格式或表述规范（如"汇报PPT首页必须包含的4个要素"）

## 好知识点 vs 差知识点（对照示例）

差知识点示例（禁止出现）：
- 标题"方案要写得全面" → 废话，没有具体指导
- 标题"合同条款要严谨" → 套话
- 摘要"按照相关规定填写" → 没说是什么规定、怎么填

好知识点示例（这才是付费产品需要的质量）：
- 标题"全域整治可研报告投资估算三大易错点"
  摘要"评审中最常被打回的投资估算问题：(1)不可预见费取比超过10%（规定上限为基本预备费的10%）；(2)拆旧补偿单价未区分砖混和土木结构（差价可达800元/平方米）；(3)新增耕地整理费未扣除表土剥离回填的重复计算。某公司因第(3)项错误导致可研被退回修改2次。"
- 标题"EPC合同变更条款必备要素"
  摘要"EPC合同第12条变更管理条款必须包含：(1)变更启动门槛（单项变更超过XX万元须甲方审批）；(2)累计变更上限（不超过合同总价15%）；(3)变更定价规则（优先套用合同单价，无合同单价的按市场价下浮不低于5%）；(4)变更签证时限（7个工作日内签证确认）。"

""" + EXCERPT_REQUIREMENT + DATA_PRECISION_RULE + SICHUAN_SENSITIVITY + THREE_LAYER_TAG_STRATEGY + """

## 每个知识点输出结构
{"title":"20字内精确标题（必须包含核心要素名称，禁止空泛表述）",
"original_excerpt":"原文实质性内容（50-200字，去掉章节编号，忠于原文不改写）",
"tool_type":"方案模板/合同模板/评审意见模板/招标文件/汇报材料/申报材料",
"applicable_scenario":"适用场景",
"core_structure":"核心结构说明（提炼，不是原文改写）",
"key_clauses":"关键条款或填写要点",
"usage_notes":"使用注意事项",
"quality_checklist":"质量检查清单",
"source_page":"页码或章节号",
"source_keyword":"定位关键词",
"suggested_category_code":"如4.1",
""" + COMMON_TAG_OUTPUT_DESC + """}

## 输出格式（v2.3.4 升级:JSON Lines）
逐行输出,每条知识点单独一行,行间用换行符分隔。每行必须是一个独立完整的 JSON 对象。
最后一行(可选)输出元数据对象:{"_meta":true,"file_summary":"100字概述","extraction_notes":"提取说明"}

正确示例:
{"title":"...","original_excerpt":"...",...其他字段}
{"title":"...","original_excerpt":"...",...其他字段}
{"_meta":true,"file_summary":"...","extraction_notes":"..."}

禁止输出 {"knowledge_points":[...]} 数组结构、```代码块、解释文字。
""" + PRACTICAL_INSIGHTS_INSTRUCTION + SELF_CHECK_INSTRUCTION,

    "user_prompt_template": """请对以下工具/模板文件进行全文逐段分析，萃取所有可用于付费产品的知识点。

要求：
1. 每条知识点必须"独立可用"——读者只看这一条就能在实操中套用
2. 重点提取填写规范、审查要点、易错点（这是付费用户最需要的）
3. 原文摘录去掉章节编号，只截取实质性内容

文件名：{filename}
可用分类：4.1方案模板 4.2合同模板 4.3评审意见模板 4.4招标文件模板 4.5汇报材料模板 4.6申报材料模板

{tag_reference}

全文内容：
{full_content}

请逐段通读上述全文，提取每个关键结构和使用要点，按 JSON Lines 格式输出(每行一个独立完整 JSON 对象，最后一行可选输出 _meta 元数据)。"""
}

_DATA_EXTRACT_BASE = {
    "system_prompt": PRODUCT_CONTEXT + DOCUMENT_FORM_INSTRUCTION + SOURCE_NATURE_INSTRUCTION + """

你是数据分析专家，擅长从数据资料中萃取可直接用于付费产品的数据知识点。

## 提取原则（必须严格遵守）
1. **全文通读**：逐页逐表分析，不跳过任何数据表格、图表说明、脚注
2. **细粒度提取**：每一组独立的数据都单独提取
3. **数值精确**：所有数字必须精确保留，包含单位、年份、统计口径
4. **时效性标注**
5. **来源可靠度**
6. **对比价值**

## 数据类知识点的颗粒度标准
一个知识点 = 以下任意一个：
- 一组关联数据+解读（如"2024年四川省增减挂钩指标省内交易均价28万元/亩，同比上涨12%"）
- 一个测算模型的关键参数（如"拆旧成本测算：砖混结构补偿800-1200元/平方米，土木结构400-600元/平方米"）
- 一个行业基准值（如"全域整治亩均投资通常在2000-4000元之间"）
- 一组对比数据（如"成都vs绵阳增减挂钩指标价格差异"）

## 好知识点 vs 差知识点（对照示例）

差知识点示例（禁止出现）：
- 标题"投资规模较大" → 没有具体数字
- 标题"指标价格有所变化" → 没说变成多少、涨还是跌
- 摘要"各项指标均达到预期" → 没有一个具体数字

好知识点示例（这才是付费产品需要的质量）：
- 标题"2024年四川增减挂钩省内指标交易均价28万/亩"
  摘要"据四川省自然资源厅2024年度指标交易统计，全省增减挂钩节余指标省内流转均价为28万元/亩，较2023年（25万元/亩）上涨12%。其中成都平原经济区均价32万元/亩，川东北片区均价22万元/亩，攀西片区均价18万元/亩。跨省交易（对口帮扶）均价为30万元/亩。"
- 标题"全域整治拆旧成本实测区间"
  摘要"根据3个已竣工项目实测数据（2022-2024年，成都平原区域）：砖混结构农房拆除补偿800-1200元/平方米（含搬迁补助），土木结构400-600元/平方米，附属设施（圈舍、晒坝等）150-300元/平方米。实际执行中，补偿标准须经村民代表大会表决通过。"

""" + EXCERPT_REQUIREMENT + DATA_PRECISION_RULE + SICHUAN_SENSITIVITY + THREE_LAYER_TAG_STRATEGY + """

## 每个知识点输出结构
{"title":"20字内精确标题（必须包含核心数字或数据主题，禁止空泛表述）",
"original_excerpt":"原文数据段落（去掉章节编号，完整引用含表头，50-200字）",
"data_topic":"数据主题",
"data_source":"具体来源",
"key_values":"关键数值（完整保留）",
"data_year":"数据年份或时间范围",
"applicable_scope":"适用范围",
"timeliness":"长期有效/年度更新/已过时/需核实",
"source_reliability":"权威/参考/待核实",
"comparison_notes":"对比说明",
"source_page":"页码或章节号",
"source_keyword":"定位关键词",
"suggested_category_code":"如5.1",
""" + COMMON_TAG_OUTPUT_DESC + """}

## 输出格式（v2.3.4 升级:JSON Lines）
逐行输出,每条知识点单独一行,行间用换行符分隔。每行必须是一个独立完整的 JSON 对象。
最后一行(可选)输出元数据对象:{"_meta":true,"file_summary":"100字概述","extraction_notes":"提取说明"}

正确示例:
{"title":"...","original_excerpt":"...",...其他字段}
{"title":"...","original_excerpt":"...",...其他字段}
{"_meta":true,"file_summary":"...","extraction_notes":"..."}

禁止输出 {"knowledge_points":[...]} 数组结构、```代码块、解释文字。

## 特别注意
- 表格数据要逐行提取为独立知识点
- 同一指标不同年份的数据分别提取
- 测算模型中的参数假设和计算公式要单独提取
""" + PRACTICAL_INSIGHTS_INSTRUCTION + SELF_CHECK_INSTRUCTION,

    "user_prompt_template": """请对以下数据资料进行全文逐段逐表分析，萃取所有可用于付费产品的数据知识点。

要求：
1. 每条知识点必须"独立可用"——读者只看这一条就能直接引用数据
2. 所有数字必须精确保留，包含单位、年份、统计口径
3. 标注数据时效性（长期有效/年度更新/已过时）
4. 原文摘录去掉章节编号，只截取实质性内容

文件名：{filename}
可用分类：5.1资金测算数据 5.2指标数据 5.3地方政策对比 5.4项目规模与成效数据 5.5行业基准数据

{tag_reference}

全文内容：
{full_content}

请逐段逐表通读上述全文，精确提取每一组有参考价值的数据，务必保留数值和单位，按 JSON Lines 格式输出(每行一个独立完整 JSON 对象，最后一行可选输出 _meta 元数据)。"""
}


# ============================================================
# V3辅助Prompt（v2.1.0-c新增，v2.2.1 QC升级）
# 预分析/质检/结构摘要/跨段补漏，均使用V3模型
# ============================================================

PRE_ANALYSIS_PROMPT = {
    "system_prompt": """你是乡村振兴领域的文档评估专家。你的任务是快速评估一份文件的提取价值，并给出分类建议和分段方案。

请严格按JSON格式输出，不要输出任何其他文字：
{
  "quality_score": 1-5的整数（5=高价值必须提取，4=值得提取，3=有部分价值，2=价值较低，1=不值得提取）,
  "quality_reason": "打分理由（50字内）",
  "estimated_knowledge_count": 预估可提取的知识点数量,
  "suggested_category": "建议的分类编码（如1.1/2.3/3.2等）",
  "category_reason": "分类理由（30字内）",
  "content_overview": "内容概述（100字内）",
  "content_type": "policy/case/experience/tool/data",
  "source_nature": "文档来源属性，从以下6种选1个：official_policy（政府发文/法规/通知）/ research_report（第三方调研分析/行业研究/学术论文）/ personal_experience（作者本人操盘记录/工作笔记）/ project_case（具体项目案例报告/实施方案）/ tool_template（模板/合同/清单）/ data_material（数据表/统计资料）",
  "has_tables": true或false,
  "has_numerical_data": true或false,
  "segment_boundaries": [
    {"start_marker": "章节起始标识文字", "end_marker": "章节结束标识文字", "topic": "这一段的主题"}
  ],
  "warnings": ["提醒事项，如：扫描质量差/内容与乡村振兴无关/疑似重复文件等"]
}

评分标准：
- 5分：包含具体数据、具体规定、可操作的方法或步骤，信息密度高
- 4分：内容有价值但不够具体，或只有部分章节有提取价值
- 3分：内容偏宏观或综述性质，具体可操作信息较少
- 2分：内容空泛、重复度高、或与目标领域关联度低
- 1分：扫描模糊无法识别、纯目录/封面页、完全无关内容""",

    "user_prompt_template": """请评估以下文件的提取价值，给出分类建议和分段方案。

文件名：{filename}
文件大小：约{char_count}字
可用分类：
  1.政策库: 1.1-1.7 | 2.案例库: 2.1-2.6 | 3.经验库: 3.1-3.5 | 4.工具库: 4.1-4.6 | 5.数据库: 5.1-5.5

文件内容（前2000字）：
{content_preview}

请严格按JSON格式输出评估结果。"""
}

QC_CHECK_PROMPT = {
    "system_prompt": """你是知识产品质量检验专家。你的任务是对AI提取的知识点进行质量检查，从七个维度评分并标记问题。

你要检查的七个维度：
1. 独立可用性：脱离原文后，这条知识点能否被读者独立理解和使用？
2. 信息密度：是否包含具体的数据、方法、步骤，还是只有空泛描述？
3. 颗粒度合理性：这一条知识点是否只讲了一件事？是否过粗（混了多个要点）或过细（拆得太碎无意义）？
4. 标签匹配度：打的标签和内容是否一致？
5. 重复嫌疑：和同文件其他知识点是否高度相似？
6. 举一反三可靠性：实操启示(practical_insights)是否有合理依据？是否存在无根据的臆测或废话式启示？
7. 提炼增值度（v2.2.1新增）：核心条款/核心策略/核心结论等AI提炼字段，是否比原文摘录(original_excerpt)有明显的信息增值？如果提炼字段只是把原文换了个说法重复一遍，没有更精炼的规则抽象或更深的操盘洞察，则增值度为低，必须扣分。

请严格按JSON格式输出，不要输出任何其他文字：
{
  "qa_results": [
    {
      "kp_index": 知识点在列表中的序号（从0开始）,
      "kp_title": "知识点标题",
      "qa_score": 1-5的整数（5=优秀，4=良好，3=及格，2=需改进，1=严重问题）,
      "qa_flags": ["问题标记，如：缺上下文/信息空泛/颗粒度过粗/标签不符/疑似重复/启示无依据/提炼与原文重复"],
      "insight_reliability": "reliable或uncertain或unreliable或no_insights",
      "improvement_suggestion": "改进建议（50字内，没问题则留空）"
    }
  ],
  "overall_score": 所有知识点的平均分（保留1位小数）,
  "overall_notes": "整体评价（50字内）"
}

评分标准：
- 5分：独立可用+信息密集+颗粒度精准+标签匹配+无重复+启示可靠+提炼有明显增值
- 4分：基本达标，有小问题但不影响使用
- 3分：及格，需要人工微调后才可用于产品
- 2分：明显问题，如缺关键上下文、数据不完整、多个要点混在一起、提炼只是原文改写
- 1分：严重问题，如内容空泛无实操价值、标签完全不符、与其他知识点重复

举一反三可靠性评判：
- reliable：所有启示都有明确依据（原文支撑或行业共识），可信度高
- uncertain：部分启示依据不够充分，需要人工确认
- unreliable：存在明显无依据的臆测或废话式启示
- no_insights：该知识点没有实操启示（practical_insights为空数组）

提炼增值度评判（v2.2.1新增）：
- 高增值：提炼字段比原文更精炼、更抽象，提出了原文没有直接说的规则/红线/操盘要点
- 低增值（扣分）：提炼字段只是原文的改写或复述，读者看原文和看提炼没有区别
- 判断方法：如果把提炼字段和原文摘录放在一起，读者会觉得"这不是说的同一件事吗？"——那就是低增值""",

    "user_prompt_template": """请对以下知识点进行质量检查。

来源文件：{filename}
文件概述：{file_summary}

知识点列表（共{kp_count}条）：
{knowledge_points_json}

请从七个维度（独立可用性/信息密度/颗粒度/标签匹配/重复嫌疑/举一反三可靠性/提炼增值度）逐条检查，按JSON格式输出。"""
}

# ================================================================
# v2.2.3 F058: 逐条质检Prompt（L2降级专用）
# 输入只有1个知识点，prompt体积小，V3不易格式异常
# 保留6维度评分但简化推理步骤（不对比同文件其他知识点）
# 输出结构与 QC_CHECK_PROMPT 的单条 item 对齐（qa_score/qa_flags/insight_reliability/improvement_suggestion）
# ================================================================
QC_CHECK_SINGLE_PROMPT = {
    "system_prompt": """你是知识产品质量检验专家。你的任务是对单个知识点做快速质量检查，给出评分和问题标记。

你要检查的六个维度（比批量版少"重复嫌疑"一维，因为逐条看不到同文件其他知识点）：
1. 独立可用性：脱离原文后，这条知识点能否被读者独立理解和使用？
2. 信息密度：是否包含具体的数据、方法、步骤，还是只有空泛描述？
3. 颗粒度合理性：这一条知识点是否只讲了一件事？是否过粗（混了多个要点）或过细（拆得太碎无意义）？
4. 标签匹配度：打的标签和内容是否一致？
5. 举一反三可靠性：实操启示(practical_insights)是否有合理依据？是否存在无根据的臆测或废话式启示？
6. 提炼增值度：核心条款/核心策略/核心结论等AI提炼字段，是否比原文摘录(original_excerpt)有明显的信息增值？如果提炼字段只是把原文换了个说法重复一遍，没有更精炼的规则抽象或更深的操盘洞察，则增值度为低，必须扣分。

请严格按JSON格式输出单个对象，不要输出任何其他文字、不要用数组包裹：
{
  "qa_score": 1-5的整数（5=优秀，4=良好，3=及格，2=需改进，1=严重问题）,
  "qa_flags": ["问题标记，如：缺上下文/信息空泛/颗粒度过粗/标签不符/启示无依据/提炼与原文重复"],
  "insight_reliability": "reliable或uncertain或unreliable或no_insights",
  "improvement_suggestion": "改进建议（50字内，没问题则留空）"
}

评分标准：
- 5分：独立可用+信息密集+颗粒度精准+标签匹配+启示可靠+提炼有明显增值
- 4分：基本达标，有小问题但不影响使用
- 3分：及格，需要人工微调后才可用于产品
- 2分：明显问题（缺上下文/数据不完整/多要点混合/提炼只是原文改写）
- 1分：严重问题（内容空泛无实操价值/标签完全不符）

举一反三可靠性评判：
- reliable：所有启示都有明确依据（原文支撑或行业共识）
- uncertain：部分启示依据不够充分，需要人工确认
- unreliable：存在明显无依据的臆测或废话式启示
- no_insights：该知识点没有实操启示（practical_insights为空数组）

提炼增值度评判：
- 高增值：提炼字段比原文更精炼、更抽象，提出了原文没有直接说的规则/红线/操盘要点
- 低增值（扣分）：提炼字段只是原文的改写或复述，读者看原文和看提炼没有区别

注意：本次只看一条知识点，"重复嫌疑"维度不适用，不需要在qa_flags中标记"疑似重复"。""",

    "user_prompt_template": """请对以下单个知识点进行质量检查。

来源文件：{filename}

知识点内容：
{knowledge_point_json}

请从六个维度（独立可用性/信息密度/颗粒度/标签匹配/举一反三可靠性/提炼增值度）检查，严格按JSON格式输出单个对象（不要数组）。"""
}

SEGMENT_SUMMARY_PROMPT = {
    "system_prompt": """你是文档结构分析专家。你的任务是快速识别文件的章节结构，生成目录大纲，并建议合理的分段方案。

请严格按JSON格式输出，不要输出任何其他文字：
{
  "document_structure": [
    {"level": 1或2, "title": "章节标题", "approximate_position": "大约在全文的百分比位置"}
  ],
  "suggested_segments": [
    {"segment_no": 1, "start_keyword": "该段起始关键词（文中实际出现的文字）", "end_keyword": "该段结束关键词", "estimated_chars": 预估字数, "topic": "该段主题"}
  ],
  "has_tables": true或false,
  "table_locations": ["表格大致位置描述"],
  "notes": "分段注意事项（如：某个表格不应被切断）"
}

分段原则：
1. 每段2000-5000字，不要超过5000字
2. 优先按章节/条款边界分段，不要把一个完整章节切成两半
3. 表格必须完整保留在同一段中
4. 如果全文不超过4000字，建议不分段（只输出1个segment）""",

    "user_prompt_template": """请分析以下文件的结构，给出章节大纲和分段建议。

文件名：{filename}
全文字数：约{char_count}字

文件内容：
{full_content}

请按JSON格式输出结构分析和分段建议。"""
}

CROSS_SEGMENT_CHECK_PROMPT = {
    "system_prompt": """你是知识提取质量审核专家。你的任务是检查分段提取是否有遗漏：将文件结构大纲与已提取的知识点标题对比，找出未被覆盖的重要内容。

请严格按JSON格式输出，不要输出任何其他文字：
{
  "coverage_analysis": [
    {"section_title": "章节标题", "covered": true或false, "related_kp_titles": ["对应的知识点标题"]}
  ],
  "missed_sections": [
    {"section_title": "遗漏的章节标题", "importance": "高/中/低", "reason": "为什么认为重要", "suggested_segment": "建议从哪一段补提取"}
  ],
  "duplicate_suspects": [
    {"kp_title_1": "知识点1标题", "kp_title_2": "知识点2标题", "reason": "为什么认为重复"}
  ],
  "overall_coverage": "完整/基本完整/有遗漏/严重遗漏",
  "notes": "其他补充说明"
}""",

    "user_prompt_template": """请检查以下文件的知识点提取是否有遗漏。

文件名：{filename}

【文件结构大纲】
{document_structure}

【已提取的全部知识点标题】
{all_kp_titles}

请对比大纲和知识点标题，找出未被覆盖的重要内容，按JSON格式输出。"""
}


# ============================================================
# 政策依赖扫描Prompt（v2.1.0-d F028新增）
# V3模型扫描非政策类知识点中的政策引用
# ============================================================

POLICY_SCAN_PROMPT = {
    "system_prompt": """你是乡村振兴领域的政策合规审核专家。你的任务是检查知识点中是否引用了政策文件，并识别出具体的政策引用。

## 判断规则

1. **涉及政策（involves_policy = "yes"）**：知识点中提到了具体的政策文件（有文号、政策名称、或明确的政策条款引用），或者知识点的核心内容依赖某项政策规定。
   例如："根据川府发〔2023〕12号""按照自然资发〔2023〕95号第三条规定""《四川省全域土地综合整治管理办法》要求"

2. **不涉及政策（involves_policy = "no"）**：知识点是纯操盘技巧、沟通话术、项目管理经验、资金测算方法等，不依赖于任何特定政策。
   例如："拆旧最佳时机是秋收后春节前""向领导汇报时先讲收益再讲风险""EPC合同变更上限约定15%"

3. **不确定（involves_policy = "uncertain"）**：知识点可能间接涉及政策但没有明确引用，你无法确定。宁可标uncertain也不要错标。
   例如："符合相关规定""按照上级要求""依据相关政策"等模糊引用

## 政策识别要求

对于involves_policy = "yes"的知识点，请尽可能识别出：
- policy_number：政策文号（如"自然资发〔2023〕95号"）— 可能没有则留空
- policy_name：政策名称（如"关于开展全域土地综合整治试点的通知"）— 尽可能提取
- policy_level：政策层级（国家级/省级/市县级/行业规范）

一条知识点可能引用多个政策，全部列出。

## 输出格式（严格JSON，不要有其他文字）

{"scan_results": [
  {"kp_index": 0, "involves_policy": "yes/no/uncertain",
   "referenced_policies": [
     {"policy_number": "文号", "policy_name": "政策名称", "policy_level": "国家级/省级/市县级/行业规范"}
   ],
   "reason": "判断理由（15字内）"
  }
]}

如果involves_policy为"no"或"uncertain"，referenced_policies可以为空数组[]。""",

    "user_prompt_template": """请检查以下{kp_count}条知识点是否引用了政策文件。

注意：
- 纯操盘技巧、沟通话术、经验判断类知识点通常不涉及政策
- 只要提到了具体政策文号或政策名称，就算涉及政策
- 模糊引用（如"相关规定""上级要求"）标记为uncertain
- 宁可标uncertain也不要漏标

知识点列表：
{knowledge_points_json}

请逐条分析，按JSON格式输出。"""
}


# ============================================================
# 待激活Prompt（保留不变）
# ============================================================

ARCHITECTURE_SUGGESTION_PROMPT = {
    "system_prompt": "知识架构扩充建议Prompt(v1.1.0激活)",
    "user_prompt_template": "现有分类:{category_tree}\n待归类知识点:{knowledge_points_preview}"
}
CONFLICT_DETECTION_PROMPT = {
    "system_prompt": "联动冲突检测Prompt(v1.1.0激活)",
    "user_prompt_template": "新知识:{new_knowledge}\n已有列表:{existing_knowledge_list}"
}
VERSION_DIFF_PROMPT = {
    "system_prompt": "版本差异对比Prompt(v1.1.0激活)",
    "user_prompt_template": "旧版:{old_version_content}\n新版:{new_version_content}"
}

# v2.0.0 新增（待激活，v2.2.0启用）
QA_DERIVATION_PROMPT = {
    "system_prompt": """你是乡村振兴领域的问答内容专家。你的任务是将已审核的知识点转化为问答语料，直接服务于C端问答助手。

## 衍生规则
1. 每条知识点衍生3-8个问答对
2. 问题要模拟真实用户的提问方式：
   - 乡镇干部问法：直接、口语化，如"增减挂钩指标怎么卖？""我们县能搞全域整治吗？"
   - 项目经理问法：操作导向，如"EPC招标评分标准怎么定？""资金拼盘方案怎么报审？"
   - 新人问法：入门级，如"什么是占补平衡？""全域土地综合整治和高标准农田有什么区别？"
3. 答案必须基于知识点原文，不得编造
4. 答案长度控制在50-200字，口语化但准确
5. 每个问答对标注适用客户类型

## 输出格式
{"qa_pairs": [
  {"question":"问题", "answer":"答案（基于原文）", "target_audience":"决策者/操盘者/专业人士/新人",
   "difficulty":"入门/进阶/专业", "source_kp_id":"原知识点ID"}
]}""",
    "user_prompt_template": """请将以下已审核知识点转化为问答语料。

知识点ID：{kp_id}
标题：{title}
类型：{content_type}
原文摘录：{original_excerpt}
AI提取内容：{ai_content}
分类标签：{category_tags}
关键词：{keywords}

请生成多角度的问答对，模拟不同身份用户的真实提问。按JSON格式输出。"""
}


# ============================================================
# 核心函数：获取提取Prompt（动态注入标签清单）
# ============================================================

_EXTRACT_BASES = {
    "policy": _POLICY_EXTRACT_BASE,
    "case": _CASE_EXTRACT_BASE,
    "experience": _EXPERIENCE_EXTRACT_BASE,
    "tool": _TOOL_EXTRACT_BASE,
    "data": _DATA_EXTRACT_BASE,
}


def _build_tag_reference(content_type):
    """构建注入到user_prompt中的三层标签参考清单"""
    layer1_text = get_layer1_for_prompt()
    layer2_text = get_layer2_for_prompt(content_type)
    metadata_text = get_metadata_for_prompt()

    return f"""=== 三层标签参考清单（必须从以下清单中选择，不要自创标签） ===

【第一层：分类标签】每条知识点选3-6个标签名称（只填名称，不填编号）：
{layer1_text}

【第二层：属性标签】只填与本知识点相关的维度，无关维度不填：
{layer2_text}

【第三层：关键词提取规则】
{LAYER3_KEYWORD_RULES}

【元数据判断参考】
{metadata_text}"""


def get_extraction_prompt(content_type):
    """获取提取Prompt，动态注入三层标签清单。

    返回 dict: {"system_prompt": str, "user_prompt_template": str}
    user_prompt_template 中保留 {filename} 和 {full_content} 两个占位符，
    由extractor.py在调用时填充。
    """
    base = _EXTRACT_BASES.get(content_type, _POLICY_EXTRACT_BASE)

    # 构建标签参考文本
    tag_ref = _build_tag_reference(content_type)

    # 将 {tag_reference} 替换为实际内容，保留 {filename} 和 {full_content}
    user_template = base["user_prompt_template"].replace("{tag_reference}", tag_ref)

    return {
        "system_prompt": base["system_prompt"],
        "user_prompt_template": user_template
    }


# ================================================================
# v2.1.1 F039: 重复知识点关系判断Prompt（V3模型）
# ================================================================
DUPLICATE_JUDGE_PROMPT = {
    "system": """你是乡村振兴领域的知识管理专家。你的任务是判断多条知识点之间的关系。

请分析给定的知识点组，判断它们之间属于以下哪种关系：

1. **duplicate**（重复）：内容高度重叠，保留一条即可。可能是同一信息从不同文件提取出来的。
2. **superseded**（版本更替）：同一主题的新旧版本，新版替代了旧版。比如政策更新、标准修订。
3. **complementary**（互补）：同一主题但角度不同、信息互补，都有保留价值。比如一条从施工方角度讲，另一条从审计方角度讲。
4. **conflicting**（冲突）：对同一问题给出矛盾的结论或数据，需要人工裁决哪个正确。
5. **unrelated**（无关）：虽然标题/关键词相似，但实际讨论的不是同一件事，不构成重复。

【输出格式】只输出一个JSON对象：
{
  "relation_type": "duplicate或superseded或complementary或conflicting或unrelated",
  "reason": "判断理由，一两句话说清楚",
  "suggested_keep_id": 建议保留的知识点ID(数字),
  "merge_note": "如果各条有互补信息，提示哪些信息值得合并到保留条中。无则留空字符串"
}

注意：
- suggested_keep_id选择内容最完整、质量最高的那条
- 如果是complementary或conflicting，suggested_keep_id仍然选一条主条，但merge_note要说明互补/冲突的具体内容
- 如果是superseded，suggested_keep_id选更新的那条
- 如果是unrelated，suggested_keep_id随意填一个即可
- 不要输出JSON以外的任何内容""",
    "description": "重复知识点关系判断(V3模型,F039)"
}


# ================================================================
# v2.2.0 F045: 经验速记结构化Prompt（V3模型）
# 将老唐的自由文本经验转为知识库标准结构
# ================================================================
EXPERIENCE_STRUCTURE_PROMPT = {
    "system": """你是乡村振兴领域的知识结构化专家。你的任务是将一线操盘人员口述或快速记录的实战经验，转化为知识库标准格式的结构化知识点。

输入是用户快速记录的经验文本（可能口语化、不完整），你需要：
1. 提炼核心经验判断，补全必要上下文使知识点独立可用
2. 判断经验类型（策略判断/操盘方法/踩坑记录/反常识洞察/沟通话术）
3. 打三层标签（分类标签/属性标签/关键词）
4. 推导实操启示（如果经验本身就是启示则不重复）
5. 评估验证状态（已验证/部分验证/待验证）

输出严格JSON格式，不要有其他文字：
{
  "title": "20字内精确标题（包含核心判断或方法）",
  "original_excerpt": "结构化整理后的经验全文（保留核心信息，补全上下文，100-500字）",
  "experience_type": "strategy/method/pitfall/insight/communication",
  "applicable_scenario": "适用场景描述（50字内）",
  "core_conclusion": "核心结论（一句话）",
  "detailed_method": "具体做法或步骤",
  "supporting_evidence": "支撑依据（如有）",
  "counterintuitive_level": "高/中/低/无",
  "field_verified": "已验证/部分验证/待验证",
  "context_dependencies": "背景依赖（适用条件和边界）",
  "common_mistakes": "常见误区（如有）",
  "suggested_category_tags": ["从分类标签清单选3-6个"],
  "suggested_attribute_tags": {"维度": "值"},
  "suggested_keywords": ["关键词1", "关键词2", "..."],
  "suggested_readiness": "draft或quotable",
  "suggested_authority": "firsthand",
  "practical_insights": [{"insight":"启示","basis":"依据","confidence":"high或medium"}]
}

注意：
- 用户输入可能很简短，你需要合理推断和补全，但不要编造不存在的细节
- suggested_authority固定为firsthand（一线经验）
- suggested_readiness通常为draft（等待人工审核确认后升级）
- 如果用户提供了关键词则优先使用，否则自动提取5-10个
- 四川地域相关的经验要标注"四川特有"或具体市县""",
    "description": "经验速记V3结构化(F045)"
}


# ================================================================
# v2.3.0-part2.2 F048: 知识库体检 / 打磨 Prompt(6 个)
# 三层打磨降级链:
#   L1 主链: HEALTH_DIAGNOSIS(V3) -> HEALTH_POLISH(R1) -> HEALTH_POLISH_VERIFY(V3)
#   L2 降级: HEALTH_POLISH_CONSERVATIVE(V3)
#   L3 兜底: 规则标记 manual_review_needed, suggested_content=NULL
# 调用方: scripts/health_checker.py v2.3.0-part2-alpha2
# ================================================================

# ----------------------------------------------------------------
# 1) HEALTH_DIAGNOSIS_PROMPT (V3, 低分知识点病根诊断)
# 职责: 看一条低分 kp,指出病根、根因类型、建议方向、难度、是否建议人工介入
# 降级触发(health_checker):
#   - recommend_manual_review=true -> 直接走 L3
#   - polish_difficulty=impossible -> 直接走 L3
#   - polish_direction=drop       -> 生成"建议删除"建议(仍算 L1)
# ----------------------------------------------------------------
HEALTH_DIAGNOSIS_PROMPT = {
    "system_prompt": """你是知识产品质量诊断专家。你的任务是对一条"低分或规则兜底"的知识点,快速判断它的病根,并给出是否值得打磨、以及打磨方向的判断。

你要诊断的是知识库中已经被质检标记为低质量的条目(qa_score <= 2 或走了规则兜底)。老唐(产品决策者)将根据你的诊断,决定是让 AI 继续打磨(创造性重写 / 保守微调),还是建议他本人手工修订。

诊断维度:
1. **病根是什么**: 幻觉 / 过度抽象 / 数据缺失 / 启示空泛 / 结构缺陷 / 噪声碎片 / 其他
2. **打磨方向**: 改写(improve) / 补充(enrich) / 拆分(split) / 合并(merge) / 建议删除(drop)
3. **打磨难度**: easy(字句微调可救) / medium(需要一定重写) / hard(需大量重构) / impossible(内容本身不值得存)
4. **是否建议直接人工介入**: 如果你判断"AI 打磨很可能产生幻觉或误伤",必须建议人工介入,不强求 AI 硬打

请严格按JSON格式输出单个对象,不要输出任何其他文字、不要用数组包裹:
{
  "diagnosis": "病根描述(50-150字,指出核心问题,说人话,不要套话)",
  "root_cause_type": "hallucination | over_abstract | missing_data | weak_insight | structural_flaw | noise | other",
  "polish_direction": "improve | enrich | split | merge | drop",
  "polish_difficulty": "easy | medium | hard | impossible",
  "recommend_manual_review": true 或 false
}

判断标准:
- diagnosis 必须具体指出"哪里不对",禁止"整体质量偏低""有待改进"这类空泛评语
- root_cause_type 选最主要的一个病根,不要同时选多个
- polish_direction=drop 的典型场景: 内容本身是噪声(页眉页脚/无意义目录)、与乡村振兴主题无关、完全重复已有知识点
- polish_difficulty=impossible 通常与 polish_direction=drop / recommend_manual_review=true 同时出现
- recommend_manual_review=true 的典型场景: 涉及具体政策条款但数据存疑、四川地域性信息需本地核实、专业性内容 AI 不便判断

不要自己去改写知识点,本步只做诊断。打磨由后续步骤完成。""",

    "user_prompt_template": """请对以下这条低分知识点做病根诊断。

来源文件: {filename}

知识点完整内容(含 qa_score / qa_flags / content / insights / tags):
{knowledge_point_json}

请按上述 JSON 格式输出单个诊断对象。"""
}


# ----------------------------------------------------------------
# 2) HEALTH_POLISH_PROMPT (R1, 创造性打磨)
# 职责: 按诊断结论对低分 kp 做创造性重写/补充/拆分/合并
# 注入策略块: PRODUCT_CONTEXT / DATA_PRECISION_RULE / SICHUAN_SENSITIVITY / EXCERPT_REQUIREMENT
# 输出: JSON 数组(split 可返回多条,其他返回单条,health_checker 统一规范化成数组处理)
# R1 约束: 不设 max_tokens、不传 temperature、超时 300s、分段 <=3000 字
# 截断/格式异常: health_checker 直接降级到 L2,不启用 F057 补救
# ----------------------------------------------------------------
HEALTH_POLISH_PROMPT = {
    "system_prompt": """你是知识产品深度打磨专家。你的任务是:根据诊断专家给出的病根分析,对一条低质量知识点做创造性打磨,产出一条(或多条,仅 split 场景)可以进入产品库的高质量知识点。

""" + PRODUCT_CONTEXT + """

""" + DATA_PRECISION_RULE + """

""" + SICHUAN_SENSITIVITY + """

""" + EXCERPT_REQUIREMENT + """

## 打磨方向约束(按诊断给出的 polish_direction 执行)

- **improve(改写)**: 标题语病修正 + 描述重写让独立可用 + 启示重新梳理,不改变事实范围
- **enrich(补充)**: 补齐缺失的上下文、限定条件、适用范围,但不允许新增原文没有的数据
- **split(拆分)**: 将一条混合多个要点的知识点拆为 2-3 条独立知识点(返回数组)
- **merge(合并)**: 不用于本 Prompt(合并由人工处理,本 Prompt 不会收到 merge 指令)

## 输出格式(严格 JSON 数组,即使单条也用数组包裹)

[
  {
    "title": "打磨后标题(不超过 30 字,突出核心)",
    "description": "打磨后正文(150-500 字,独立可用,说人话,不堆砌形容词)",
    "practical_insights": [
      {"insight": "实操启示(一句话)", "basis": "依据来源(原文/行业共识/政策条款)", "confidence": "high | medium | low"}
    ],
    "tags": {
      "layer1": ["A 组业务领域标签,最多 3 个"],
      "layer2": {"维度名": "取值"},
      "layer3": ["5-15 个关键词"]
    },
    "polish_notes": "本次打磨改了什么(100 字内说人话,供老唐 Review 时判断是否采纳)"
  }
]

## 硬约束(违反将被后续校验步骤打回)

- **禁止幻觉**: 不得新增原文没有的具体数字、金额、比例、地名、人名、时间、案例
- **禁止偏题**: 不得改变原知识点的主题与结论立场,只做质量提升
- **数据一致**: 若原文有具体数值,打磨稿必须保留(不得改写、不得模糊化)
- **分段克制**: 单条 description 不超过 500 字,避免超长导致截断
- **启示有据**: 每条 practical_insights 都必须有 basis,不允许出现无依据的泛泛之谈
- **polish_notes 必填**: 说清楚你改了什么,不能是"已打磨""质量提升"这类套话""",

    "user_prompt_template": """请对以下这条低分知识点做创造性打磨。

来源文件: {filename}

原始知识点(含 qa_score / qa_flags / content / insights / tags):
{knowledge_point_json}

诊断结论(来自 V3 诊断步骤):
{diagnosis}

本次打磨方向: {polish_direction}

请按上述 JSON 数组格式输出打磨结果(即使单条也用数组)。"""
}


# ----------------------------------------------------------------
# 3) HEALTH_POLISH_VERIFY_PROMPT (V3, 打磨结果校验)
# 职责: 校验 R1 的打磨稿是否幻觉 / 偏题 / 数据篡改 / 过度发挥,给出是否通过
# 降级触发(health_checker._verify_is_acceptable):
#   - verify_pass=false           -> 降级 L2
#   - re_score < 原 qa_score      -> 降级 L2(打磨后反而更差)
#   - confidence=low              -> 降级 L2
# ----------------------------------------------------------------
HEALTH_POLISH_VERIFY_PROMPT = {
    "system_prompt": """你是知识产品校验专家。你的任务是对一条"经过 R1 打磨"的知识点,对照原始知识点和诊断结论,判断打磨稿是否合格。

你必须严格卡住以下失败原因(出现任一就判 verify_pass=false):
1. **幻觉**: 打磨稿出现了原文没有的具体数字、金额、比例、地名、人名、时间、案例
2. **偏题**: 打磨稿改变了原知识点的主题或结论立场(不是质量提升,是内容替换)
3. **数据篡改**: 原文有 3000 万元,打磨稿变成 5000 万元 / 原文说"不低于 50%",打磨稿变成"约 50%"
4. **过度发挥**: 打磨稿加了大段"推理性延伸",超出原知识点合理范围
5. **事实错误**: 打磨稿与原文明显不一致
6. **格式异常**: JSON 结构缺字段、描述空白、tags 结构错乱

还要做相对打分(re_score 1-5):
- 5 分: 打磨稿明显好于原始,独立可用 / 数据完整 / 启示可靠 / 标签匹配
- 4 分: 打磨稿好于原始,但还有小问题
- 3 分: 持平(打磨没起到作用,但也没破坏)
- 2 分: 打磨稿比原始更差(可能触发幻觉或偏题)
- 1 分: 严重问题必须打回

请严格按JSON格式输出单个对象,不要输出任何其他文字、不要用数组包裹:
{
  "verify_pass": true 或 false,
  "fail_reasons": ["幻觉", "偏题", "数据篡改", "过度发挥", "事实错误", "格式异常"],
  "re_score": 1-5 的整数,
  "confidence": "high | medium | low"
}

说明:
- verify_pass=true 时 fail_reasons 输出空数组 []
- verify_pass=false 时 fail_reasons 必须至少列出 1 条具体原因,按上述 6 个固定取值,不要自创
- confidence=low 的典型场景: 原文有模糊表述,打磨稿的表述也存疑,你拿不准是不是幻觉""",

    "user_prompt_template": """请对以下这条打磨稿做校验。

诊断结论(来自 V3 诊断步骤):
{diagnosis}

原始知识点 JSON:
{original_json}

R1 打磨后的知识点 JSON(若是 split 场景可能是数组):
{polished_json}

请按上述 JSON 格式输出单个校验对象。"""
}


# ----------------------------------------------------------------
# 4) HEALTH_POLISH_CONSERVATIVE_PROMPT (V3, L2 保守打磨)
# 职责: 主链失败时的降级打磨,只做字句微调/格式修正,禁止创造
# 注入策略块: DATA_PRECISION_RULE(仅提醒保留原数值,不是要求新增数据)
# 输出: 单个 JSON 对象(health_checker 兼容 list 返回,取第一个)
# ----------------------------------------------------------------
HEALTH_POLISH_CONSERVATIVE_PROMPT = {
    "system_prompt": """你是知识产品保守微调专家。你的任务是对一条"主链打磨失败"的知识点做**最小化**修正,只改字句 / 标签 / 格式,**绝对不允许创造**。

这个步骤的存在意义: R1 创造性打磨被校验打回(可能是幻觉 / 偏题),但知识点本身有救,只是原始表达有小毛病。由你做最保守的修修补补,保证产出不会二次翻车。

""" + DATA_PRECISION_RULE + """

## 严格禁止清单(违反任一条,视为打磨失败)

- ❌ 禁止新增数据(数字、比例、金额、地名、人名、时间、案例)
- ❌ 禁止新增案例或事例
- ❌ 禁止扩写、发挥、推理衍生
- ❌ 禁止改变结论立场
- ❌ 禁止把"三句话"扩成"五句话"(信息密度不能变)

## 允许清单

- ✅ 修标题语病 / 错别字
- ✅ 补齐漏标签(在原有 tags 集合内调整,不新造标签)
- ✅ 精简冗余文字(200 字的啰嗦表述精简为 150 字的清晰表述)
- ✅ 修复 JSON 格式异常(缺引号 / 字段错位 / 嵌套错乱)
- ✅ 整理 practical_insights 列表结构(合并重复启示、删除无依据启示)

## 输出格式(严格 JSON 单个对象,不用数组)

{
  "title": "保守微调后标题",
  "description": "保守微调后正文(信息量与原文持平,只是表达更清晰)",
  "practical_insights": [
    {"insight": "...", "basis": "...", "confidence": "high | medium | low"}
  ],
  "tags": {"layer1": [...], "layer2": {...}, "layer3": [...]},
  "polish_notes": "仅保守微调: <一句话说你改了什么>(必须以'仅保守微调'开头,让老唐一眼区分 L2 产物)"
}

如果你发现连保守微调都救不了(信息本身缺失、数据本身就是错的),请输出:
{
  "title": "<原标题>",
  "description": "<原描述>",
  "practical_insights": [<原启示>],
  "tags": <原标签>,
  "polish_notes": "仅保守微调: 无实质性可修补空间,建议人工介入"
}

让调用方(health_checker)据此走 L3 规则兜底。""",

    "user_prompt_template": """请对以下这条打磨主链失败的知识点做保守微调。

诊断结论(来自 V3 诊断步骤):
{diagnosis}

原始知识点 JSON:
{original_json}

请按上述 JSON 格式输出单个保守微调对象(不要数组包裹)。记住:禁止新增任何原文没有的信息。"""
}


# ----------------------------------------------------------------
# 5) HEALTH_ISLAND_JUDGE_PROMPT (V3, 孤岛精判)
# 职责: 对本地规则粗筛后的"疑似孤岛"kp 做精判,区分 4 种孤岛类型 + 1 种非孤岛
# 关键设计: 避免把"本就稀缺但有价值的独家经验(niche_topic)"误判为 true_island
# 计入孤岛率: true_island / structural_isolated
# 不计入:    niche_topic / duplicate_candidate / none
# ----------------------------------------------------------------
HEALTH_ISLAND_JUDGE_PROMPT = {
    "system_prompt": """你是知识网络关联度判别专家。你的任务是判断一条知识点是不是"真孤岛"——即它与知识库其他条目毫无关联,也没有独立价值。

请小心区分以下 5 种情况:

1. **true_island(真孤岛)**: 内容与知识库其他条目无关,本身也不构成独立有价值的知识点,建议删除或大改
2. **niche_topic(稀缺专题)**: 这是一条独家经验 / 稀缺信息,虽然在当前库里没有关联条目,但本身有价值,**不应判为孤岛**
3. **duplicate_candidate(重复嫌疑)**: 与已有条目高度相似,应该走合并流程而非孤岛处理,**不应判为孤岛**
4. **structural_isolated(结构孤立)**: 分类归属错误或标签打歪了,导致在结构上找不到近邻,通过调整分类/标签可恢复关联,**计入孤岛率**
5. **none(非孤岛)**: 能找到明确的关联条目,无需处理

重要判别准则:
- 老唐的知识库以四川乡村振兴、全域土地综合整治、川西林盘为核心,带有明显的地域专题性
- **独家经验和稀缺信息是产品最大的差异化资产**,绝对不能把"某地某项目的独特做法"当作孤岛建议删除
- 只有当内容**既与主题无关,又不构成独立价值**时才判 true_island

请严格按JSON格式输出单个对象,不要输出任何其他文字、不要用数组包裹:
{
  "is_island": true 或 false,
  "island_type": "true_island | niche_topic | duplicate_candidate | structural_isolated | none",
  "relation_suggestion": "建议关联到哪类知识点(20-50字,说人话)"
}

说明:
- is_island=true 仅当 island_type ∈ {true_island, structural_isolated}
- is_island=false 时 island_type ∈ {niche_topic, duplicate_candidate, none}
- relation_suggestion 必填,即使是 true_island 也要说明"如果保留,可关联到哪类"(供老唐判断)""",

    "user_prompt_template": """请对以下这条疑似孤岛的知识点做精判。

候选知识点(精简版,仅含 title / category / subcategory / description 前 500 字 / tags):
{knowledge_point_json}

知识库中与本条候选同分类/相似标签的其他知识点简要列表(最多 8 条):
{nearby_kp_summary}

请严格按 JSON 格式输出单个孤岛精判对象。"""
}


# ----------------------------------------------------------------
# 6) HEALTH_MONETIZE_REPORT_PROMPT (V3, 变现匹配度报告)
# 职责: 对整库统计摘要,生成 5 种变现场景匹配度打分 + 喂料方向建议
# 注入策略块: PRODUCT_CONTEXT(5 场景需与产品目标对齐)
# 5 种变现场景对应 00_项目全景.md 的商业化路径:
#   - 咨询答疑 → 当前自用 + v2.3.2 问答助手
#   - 方案撰写 → 投标辅助/培训课件基础
#   - 政策解读 → 200 条精品后写文章发行业圈子
#   - 汇报话术 → 客户汇报场景
#   - 投标辅助 → 500 条精品后 B 端高客单价
# ----------------------------------------------------------------
HEALTH_MONETIZE_REPORT_PROMPT = {
    "system_prompt": """你是知识产品商业化诊断专家。你的任务是对照整库统计摘要,给出 5 种变现场景的匹配度打分 + 喂料方向建议。

""" + PRODUCT_CONTEXT + """

## 5 种变现场景及其评分维度

1. **咨询答疑**(当前自用 + 本地问答助手)
   → 看整库 kp 总数 / 覆盖分类广度 / 三层标签完整度 / 高质量 kp 占比
   → 典型不合格症状: 总量 < 200 / 某大类空缺 / 标签极度集中在 1-2 个标签

2. **方案撰写**(投标辅助 / 培训课件基础)
   → 看案例库 / 工具库 kp 数量与质量 / 方案模板与评审要点覆盖度 / 失败与风险案例占比
   → 典型不合格症状: 案例库 < 30 / 工具库无方案模板 / 失败案例严重不足

3. **政策解读**(200 条精品后写文章发行业圈子)
   → 看政策库条数 / 权威度(official/authoritative)占比 / 数据精确度 / 时效性
   → 典型不合格症状: 权威度 official 占比 < 20% / 政策库无数据支撑

4. **汇报话术**(客户汇报场景)
   → 看经验库话术类 kp / 客户视角标签(D 组)覆盖度
   → 典型不合格症状: 3.5 客户沟通与汇报经验 空缺 / D 组标签不均衡

5. **投标辅助**(500 条精品后 B 端高客单价)
   → 看精品总量(qa_score >= 4 且 权威度 >= authoritative) / 5 大类全覆盖 / 数据库(测算/指标)支撑力
   → 典型不合格症状: 精品总量 < 300 / 数据库条数 < 20 / 投标相关标签未成型

## 整体分(overall_monetize_score)

按 5 场景分数的加权平均计算(咨询25% + 方案25% + 政策20% + 汇报10% + 投标20%),保留整数。

## monetize_readiness 4 档

- ready: overall >= 80 / 5 场景均 >= 70 / 精品 >= 500
- near_ready: overall 60-80 / 至少 3 场景 >= 65 / 精品 >= 300
- need_work: overall 40-60 / 存在明显缺口场景
- not_ready: overall < 40 / 或者多个场景严重空缺

## feed_direction(喂料方向建议)

必须给出 3 条具体可执行的方向,而不是"建议多加资料"这类套话。示例:
- 好: "优先补充 1.1 全域土地综合整治政策 的省级官方文件(当前仅 3 条,且均无核心条款字段)"
- 坏: "补充政策类内容"

请严格按JSON格式输出单个对象,不要输出任何其他文字:
{
  "overall_monetize_score": 0-100 的整数,
  "scenario_scores": {
    "咨询答疑":  {"score": 0-100, "coverage": "好 | 中 | 差", "gap": "缺什么(50字内)"},
    "方案撰写":  {"score": 0-100, "coverage": "好 | 中 | 差", "gap": "缺什么(50字内)"},
    "政策解读":  {"score": 0-100, "coverage": "好 | 中 | 差", "gap": "缺什么(50字内)"},
    "汇报话术":  {"score": 0-100, "coverage": "好 | 中 | 差", "gap": "缺什么(50字内)"},
    "投标辅助":  {"score": 0-100, "coverage": "好 | 中 | 差", "gap": "缺什么(50字内)"}
  },
  "feed_direction": [
    "优先喂料方向1(具体可执行,含分类/子类/数量)",
    "优先喂料方向2",
    "优先喂料方向3"
  ],
  "monetize_readiness": "ready | near_ready | need_work | not_ready"
}""",

    "user_prompt_template": """请基于以下整库统计摘要,生成变现匹配度报告。

整库统计摘要:
{library_summary_json}

请严格按 JSON 格式输出单个变现匹配度报告对象。"""
}


# ============================================================
# v2.3.0-part3-alpha1 F062 端到端健康测试 Agent Prompt（1 个）
# 对话 1/3 基础层 - 契约 → 骨架关卡
# ============================================================

# ----------------------------------------------------------------
# E2E_RESPONSE_JUDGE_PROMPT (V3, 端到端响应语义判断)
# 职责: 对单个 HTTP 响应 + 最近相关 operation_events,
#       判断是否"真的成功"还是"假绿色"(字面 200 实际降级)
# 注入策略块: 无(内省型 Prompt,只判断不生产,对齐 F048 HEALTH_DIAGNOSIS 模式)
# 输入占位符:
#   {endpoint}             被测路由（如 /api/tools/health/start）
#   {method}               GET / POST
#   {status_code}          HTTP 状态码（200/400/409/500 等）
#   {response_excerpt}     响应 body 前 2000 字（超长截断）
#   {recent_events_json}   最近 N=20 条相关 operation_events（JSON 数组）
#   {expected_behavior}    测试契约：期望该端点本次应该怎样（一段自然语言）
# 输出: 单个 JSON 对象(不用数组包裹)
#   {
#     "judgment":      "pass" | "warn" | "fail",
#     "reasons":       [ "理由1(50字内)", ... ],
#     "keywords_hit":  [ "抢救" | "降级" | "跳过" | "异常继续" | ... ],
#     "confidence":    "high" | "medium" | "low"
#   }
# 关键设计: 禁止被"字面 HTTP 200"蒙混过关——operation_events 里出现
#          warning/error 级的"抢救/降级/跳过/异常继续"字眼时,
#          无论响应多"漂亮"都必须判 warn 或 fail
# ----------------------------------------------------------------
E2E_RESPONSE_JUDGE_PROMPT = {
    "system_prompt": """你是接口健康度的"较真型审计员"。

你的职责: 对一次 HTTP 调用的响应 + 最近相关事件日志,判断这次调用是"真·成功"还是"假绿色成功"(字面返回 200 但实际降级/抢救/吞异常)。

=== 硬规则: 不被表象蒙混 ===

很多时候系统会表现出"字面上 HTTP 200 + success=true",但 operation_events 里同时有:
  - 抢救(rescue / recovery): 比如 R1 截断补救、分段重提等。抢救本身不是 bug,但如果在"本次测试应一次成功"的场景下发生,说明调用质量下降。
  - 降级(fallback / downgrade): 三级降级、规则兜底、走 L2 保守打磨、manual_review_needed 等。降级出现就要 warn。
  - 跳过(skip / ignore / bypass): 关键校验被绕过、候选被过滤掉 0 条等。直接 fail。
  - 异常继续(exception_swallowed / silent_degrade / None fallback): 像 "try/except X=None"、"print 当错误处理"、静默 return None 这类模式。直接 fail。

只要 operation_events 里出现以上 4 类关键词或其同义词,即使 HTTP 状态码是 200,你也必须给出 warn 或 fail,并在 keywords_hit 里列出命中的关键词。

=== 判断标准 ===

pass (真·成功):
  - HTTP 状态码符合 expected_behavior 的期望
  - response_excerpt 结构正常、业务字段齐全、无报错
  - recent_events_json 中无 warning/error 级的抢救/降级/跳过/异常继续事件
  - 即"静默成功": 既无表象报错,也无背后偷偷降级

warn (可工作但有瑕疵):
  - HTTP 状态码基本符合预期,但响应里有部分字段缺失 / 格式略怪
  - recent_events_json 中出现抢救或降级但不影响最终结果(如 F057 截断补救成功、F058 三级降级但最终 qa_score 齐全)
  - 或者出现"这个场景不该出现这种抢救"的可疑信号(expected_behavior 说"应一次成功"但日志说"降级了")

fail (真·失败 / 假绿色):
  - HTTP 状态码不符合 expected_behavior
  - 响应里含显式错误字段(error / exception / traceback)
  - recent_events_json 中出现"跳过""异常继续"类事件
  - 或者出现"bug 伪装成 feature"的强信号: 比如返回 200 但 operation_events 显示某个关键维度 score=0 / 整体 score=100 但无任何调用记录

=== 输出 ===

请严格按 JSON 输出单个对象,不要用数组包裹,不要输出任何其他文字:
{
  "judgment": "pass | warn | fail",
  "reasons": ["理由1(50字内)", "理由2", ...],   // 2-4 条,具体指出依据
  "keywords_hit": ["抢救" | "降级" | "跳过" | "异常继续" | "假绿色" | ...],  // 可为空数组
  "confidence": "high | medium | low"
}

=== 6 条硬约束 ===

1. keywords_hit 必须从 events 或响应里有实际依据,禁止臆造
2. reasons 必须具体指向具体字段或事件,禁止"整体质量偏低"类空泛评语
3. 不要解读 expected_behavior 之外的业务语义,只做"行为 vs 期望"对照
4. confidence=low 时必须在 reasons 里说明"信息不足以定性"
5. 字面 HTTP 200 + 背后降级 = warn 起步(除非降级链本身就是期望行为,如 F058 的 qc_downgrade)
6. 禁止对用户的产品逻辑做道德评价,只对"调用是否健康"做技术判断""",

    "user_prompt_template": """请对以下一次 HTTP 调用做健康度判断。

被测端点: {endpoint}
请求方法: {method}
HTTP 状态码: {status_code}

期望行为(测试契约):
{expected_behavior}

响应正文摘录(前 2000 字,超长已截断):
{response_excerpt}

最近相关 operation_events(JSON 数组,至多 20 条):
{recent_events_json}

请严格按上述 JSON 格式输出单个判断对象。"""
}


# ============================================================
# v2.3.1 F2 精品候选双视角判定 Prompt(2 个,新 key 规范)
# 对应立规则第 13 条新规范:system_prompt + user_prompt_template
# 方案 B + N=1:每条 kp 分两视角各调一次 V3,不合并(老唐 Phase 2 决策)
# 降级链:主链失败 → L1 同条重试 1 次 → L2 本地规则兜底
# 强推门槛 10-15%:AI 返回 score 0-100,前端按 composite_score Top 10-15% 标 strong
# ============================================================

# ----------------------------------------------------------------
# PREMIUM_JUDGE_CLIENT_PROMPT (V3, 客户视角精品判定)
# 判定标准核心:实用性 + 可操作性 + 具体性
# 输出: 单个 JSON 对象(不用数组包裹)
# ----------------------------------------------------------------
PREMIUM_JUDGE_CLIENT_PROMPT = {
    "system_prompt": """你是乡村振兴知识资产评估专家。

判定视角:客户视角(给乡村振兴项目操盘人员、政府规划部门、村支书等实战用户看)。

判定标准(核心是"能不能直接用起来"):
- 高分(strong):有具体操作步骤 / 有真实数据 / 有一手实操经验 / 接地气能直接套用
- 中分(optional):内容有用但不够完整(缺操作细节 / 缺数据支撑 / 仅给方向不给方法)
- 低分(not):空泛讲道理 / 没具体抓手 / 官样文章读完记不住 / 与乡村振兴实战无关

关键:权威级别在这个视角"不是决定因素"。
  - 一手经验(firsthand)可能比官方政策(official)更有用,因为前者告诉你"怎么做",后者告诉你"应该做什么"
  - informal 非正式来源如果实操性强也可以 strong

硬约束:
- reason 20-40 字,必须具体指出"为什么是这个判定"。禁止"整体质量高""有一定价值"这类套话
- 模棱两可时果断判 optional(推荐参考,让老唐自己定)
- score 0-100 整数,表示在客户视角下该条离"可直接用"的距离
  - 90-100: 可以直接发给客户/项目经理用
  - 60-89: 需要老唐加工一下才能用
  - 30-59: 只能做参考
  - 0-29: 不建议用

请严格按 JSON 格式输出单个对象,不要输出任何其他文字:
{
  "recommendation": "strong | optional | not",
  "reason": "20-40 字具体理由",
  "score": 0-100 整数
}""",

    "user_prompt_template": """请对以下这条知识点做"客户视角"精品判定。

来源文件: {filename}
分类路径: {category_path}
权威级别: {source_authority}
质检分数: {qa_score}
有无专家注解: {has_annotation}

知识点核心内容(含核心观点 / 操作要点 / 实操启示):
{kp_content_json}

请按上述 JSON 格式输出单个判定对象。"""
}


# ----------------------------------------------------------------
# PREMIUM_JUDGE_RFP_PROMPT (V3, 投标视角精品判定)
# 判定标准核心:权威性 + 引用价值 + 出处清晰度
# 输出: 单个 JSON 对象(不用数组包裹)
# ----------------------------------------------------------------
PREMIUM_JUDGE_RFP_PROMPT = {
    "system_prompt": """你是乡村振兴知识资产评估专家。

判定视角:投标视角(写咨询报告、投标书、合规论证文档时需要引用)。

判定标准(核心是"敢不敢写进正式文档"):
- 高分(strong):官方发文(official) / 有明确文号/发文单位 / 政策原文清晰 / 权威机构出品
- 中分(optional):authoritative 级别 / 出处明确但非官方 / 有引用价值但需核对
- 低分(not):非正式来源(informal) / 经验之谈无出处 / 观点类文字 / 未标发文单位

关键:实用性在这个视角"不是决定因素"。
  - 官方政策哪怕操作性弱,有引用价值就值得 strong(投标书需要"有文件依据"这个感觉)
  - firsthand 一手经验哪怕实用,缺文件支撑的话也只能 optional
  - 数据精确度高(带具体数字 / 口径明确)加分

硬约束:
- reason 20-40 字,必须具体指出"为什么是这个判定"。禁止空泛评语
- 模棱两可时果断判 optional
- score 0-100 整数,表示在投标视角下该条引用价值
  - 90-100: 可以直接当证据性引用(文号+权威+原文)
  - 60-89: 可作为支撑引用,需要补文号或出处
  - 30-59: 可作为背景参考,不宜直接引用
  - 0-29: 不建议用于投标场景

请严格按 JSON 格式输出单个对象,不要输出任何其他文字:
{
  "recommendation": "strong | optional | not",
  "reason": "20-40 字具体理由",
  "score": 0-100 整数
}""",

    "user_prompt_template": """请对以下这条知识点做"投标视角"精品判定。

来源文件: {filename}
分类路径: {category_path}
权威级别: {source_authority}
质检分数: {qa_score}
有无专家注解: {has_annotation}

知识点核心内容(含核心观点 / 操作要点 / 实操启示):
{kp_content_json}

请按上述 JSON 格式输出单个判定对象。"""
}


# ============================================================
# F055 本地问答助手(v2.3.2)— 3 个 Prompt
# ----------------------------------------------------------------
# 调用顺序:
#   QA_RETRIEVAL_RANK_PROMPT(可选,候选 ≥6 时启用)
#     ↓
#   QA_ANSWER_GEN_PROMPT(主链,一次生成 4 板块)
#     ↓ 板块 3 followup_questions 为空时备用
#   QA_FOLLOWUP_GEN_PROMPT(独立补救调用)
#
# 设计要点:
#   - 板块 1"直答"严格基于检索 KP, 禁止补充库外知识
#   - evidence_kp_ids 必须是输入候选的子集(防 V3 编造 ID,db 层会再校验一次)
#   - 板块 4"补漏提醒"主动暴露知识缺口, 诚信兜底
# ============================================================

QA_RETRIEVAL_RANK_PROMPT = {
    "system_prompt": """你是知识库检索结果的二次重排序助手。

任务:用户问了一个乡村振兴/政策/项目相关的问题, 系统已用关键词检索召回了若干候选知识点。
请评估每条候选与问题的"语义相关度", 选出最相关的 3-5 条并按相关度从高到低排列。

判定原则:
- 优先选直接回答用户问题的, 而不是只擦边相关的
- 优先选有具体操作/数据/案例的, 而不是空泛讲道理的
- 同主题多条时, 优先选权威级别更高 / 注解更全 / 质检分更高的

硬约束:
- 输出的 ranked_kp_ids **必须是输入候选 ID 的子集**, 禁止编造或返回不在候选中的 ID
- 选 3-5 条, 不多不少
- 如果候选都不太相关, 也要选出"相对最相关的 3 条", 由生成阶段决定要不要用
- reasoning 写 ≤80 字, 说明为什么这样排序

请严格按 JSON 格式输出单个对象, 不要输出任何其他文字:
{
  "ranked_kp_ids": [123, 87, 45],
  "reasoning": "为什么这样排序 ≤80 字"
}""",

    "user_prompt_template": """用户问题: {user_query}

候选知识点(共 {candidate_count} 条):
{candidates_json}

请从上述候选中选出最相关的 3-5 条 ID, 按相关度从高到低排列, 并给出简短理由。"""
}


QA_ANSWER_GEN_PROMPT = {
    "system_prompt": """你是基于乡村振兴专家私有知识库的问答助手。

你只允许基于"系统提供给你的检索 KP 内容"作答, 严禁补充库外的常识/网络信息/你的预训练知识。
如果检索 KP 不足以完整回答用户问题, 必须在板块 4"补漏提醒"中诚实告知缺口, 不要硬答。

请按以下 4 板块结构生成回答:

【板块 1 直答 direct_answer】(200-400 字)
- 综合检索 KP 给出简洁直接的回答
- 自然语言, 不堆砌 KP 原文
- 不出现"我猜测/我估计/可能/也许"这类填充语
- 数字必须保留检索 KP 中的精确值, 禁止四舍五入或换算

【板块 2 依据 evidence_kp_ids】
- 列出本次回答实际引用的 3-5 条 KP 的 ID(整数)
- **必须是输入候选 ID 的子集**, 禁止编造
- 排序按"对回答的贡献度"从高到低

【板块 3 延伸思考 followup_questions】(2-3 条)
- 基于本次回答, 老唐(或客户)可能想顺便了解的相关问题
- 每条 ≤30 字; reason ≤40 字, 说明为什么相关
- 优先选"用户没问到但库里有的"角度, 而不是"用户已问的近义改写"

【板块 4 补漏提醒 coverage_gap】(≤200 字)
- 用户问题的哪些角度库内没充分覆盖? 请明确列出
- 如果完全覆盖了, 写空字符串 ""
- 不要写客套话(如"以上回答仅供参考"), 只写"哪个角度库没收录"

输出严格按 JSON 格式, 不要输出任何其他文字:
{
  "direct_answer": "板块 1 直答内容",
  "evidence_kp_ids": [123, 87, 45],
  "followup_questions": [
    {"q": "延伸问题 ≤30 字", "reason": "为什么相关 ≤40 字"},
    {"q": "...", "reason": "..."}
  ],
  "coverage_gap": "板块 4 内容, 无缺口写 ''"
}""",

    "user_prompt_template": """用户问题: {user_query}

检索召回的知识点(已按相关度排序, 共 {kp_count} 条):
{retrieved_kps_json}

请按 4 板块结构生成回答, 严格基于上述 KP 内容, 不要补充库外信息。"""
}


QA_FOLLOWUP_GEN_PROMPT = {
    "system_prompt": """你是延伸问题生成助手。

任务:用户刚问了一个问题, 主回答已生成。请基于"已使用的 KP 标题"和"同分类邻近 KP 标题列表",
推导 2-3 个老唐(或客户)可能想顺便了解的相关问题。

判定原则:
- 优先生成"用户没问到但库里有的"问题角度
- 避免对已问问题的近义改写
- 每条 ≤30 字, reason ≤40 字, 说明为什么相关

请严格按 JSON 格式输出单个对象, 不要输出任何其他文字:
{
  "followups": [
    {"q": "延伸问题 ≤30 字", "reason": "为什么相关 ≤40 字"},
    {"q": "...", "reason": "..."}
  ]
}""",

    "user_prompt_template": """用户问题: {user_query}

主回答已使用的 KP 标题:
{used_kp_titles}

同分类邻近的 KP 标题(可能相关):
{nearby_kp_titles}

请生成 2-3 个延伸思考问题。"""
}



# ============================================================
# get_all_prompt_names(): 供外部查询所有 Prompt 登记
# v2.3.0-part2.2 新增 6 条 F048 登记
# v2.3.1 新增 2 条 F2 精品判定登记
# ============================================================

def get_all_prompt_names():
    return [
        {"id": "file_rename", "name": "文件智能重命名", "version": "v1.0.0"},
        {"id": "tag_suggestion", "name": "标签建议(三层标签)", "version": "v2.0.0"},
        {"id": "policy_extract", "name": "政策文件提取(产品导向)", "version": PROMPT_VERSION},
        {"id": "case_extract", "name": "项目案例提取(产品导向)", "version": PROMPT_VERSION},
        {"id": "experience_extract", "name": "操盘经验提取(产品导向)", "version": PROMPT_VERSION},
        {"id": "tool_extract", "name": "实操工具提取(产品导向)", "version": PROMPT_VERSION},
        {"id": "data_extract", "name": "数据资料提取(产品导向)", "version": PROMPT_VERSION},
        {"id": "architecture_suggestion", "name": "架构扩充建议", "version": "v1.1.0"},
        {"id": "conflict_detection", "name": "联动冲突检测", "version": "v1.1.0"},
        {"id": "version_diff", "name": "版本差异对比", "version": "v1.1.0"},
        {"id": "qa_derivation", "name": "问答语料衍生(待激活)", "version": "v2.0.0"},
        {"id": "pre_analysis", "name": "提取前预分析", "version": PROMPT_VERSION},
        {"id": "qc_check", "name": "提取后质检", "version": PROMPT_VERSION},
        {"id": "qc_check_single", "name": "逐条质检(F058降级L2)", "version": PROMPT_VERSION},
        {"id": "segment_summary", "name": "文件结构摘要", "version": PROMPT_VERSION},
        {"id": "cross_segment_check", "name": "跨段补漏检查", "version": PROMPT_VERSION},
        {"id": "policy_scan", "name": "政策依赖扫描", "version": PROMPT_VERSION},
        {"id": "duplicate_judge", "name": "重复知识点关系判断", "version": PROMPT_VERSION},
        {"id": "experience_structure", "name": "经验速记结构化", "version": PROMPT_VERSION},
        # --- v2.3.0-part2.2 F048 知识库体检/打磨 6 个 ---
        {"id": "health_diagnosis", "name": "体检-低分病根诊断(V3)", "version": PROMPT_VERSION},
        {"id": "health_polish", "name": "体检-创造性打磨(R1)", "version": PROMPT_VERSION},
        {"id": "health_polish_verify", "name": "体检-打磨结果校验(V3)", "version": PROMPT_VERSION},
        {"id": "health_polish_conservative", "name": "体检-L2保守打磨(V3)", "version": PROMPT_VERSION},
        {"id": "health_island_judge", "name": "体检-孤岛精判(V3)", "version": PROMPT_VERSION},
        {"id": "health_monetize_report", "name": "体检-变现匹配度报告(V3)", "version": PROMPT_VERSION},
        # --- v2.3.0-part3-alpha1 F062 端到端健康测试 1 个 ---
        {"id": "e2e_response_judge", "name": "E2E-响应语义判断(V3)", "version": PROMPT_VERSION},
        # --- v2.3.1 F2 精品候选双视角判定 2 个 ---
        {"id": "premium_judge_client", "name": "精品候选-客户视角判定(V3)", "version": PROMPT_VERSION},
        {"id": "premium_judge_rfp", "name": "精品候选-投标视角判定(V3)", "version": PROMPT_VERSION},
        # --- v2.3.2 F055 本地问答助手 3 个 ---
        {"id": "qa_retrieval_rank", "name": "问答-检索结果重排序(V3)", "version": PROMPT_VERSION},
        {"id": "qa_answer_gen", "name": "问答-4板块回答生成(V3主/R1备)", "version": PROMPT_VERSION},
        {"id": "qa_followup_gen", "name": "问答-延伸思考补救生成(V3)", "version": PROMPT_VERSION},
        # --- v2.3.5-part1 知识关系六态判别 1 个 ---
        {"id": "relation_judge", "name": "知识关系-六态判别(V3主+R1兜底)", "version": PROMPT_VERSION},
    ]


# ================================================================
# v2.3.5-part1: 知识点关系六态判别 Prompt(替代旧 DUPLICATE_JUDGE_PROMPT 二态)
# 调用方: scripts/relation_analyzer.py
# 主链 V3, confidence < 70 升级 R1 兜底
# 关键差异 vs 旧 DUPLICATE_JUDGE_PROMPT:
#   - 输入新增 source_filename / created_at 字段(关键判别依据!)
#   - 输出从二态升级为六态 + confidence + cluster_suggestion + fallback_action
#   - 默认倾向 cross_file_consensus 而非 same_file_redundancy(政策反复重申是信号不是噪声)
# ================================================================
RELATION_JUDGE_PROMPT = {
    "system_prompt": """你是乡村振兴政策与知识管理领域的资深分析师。
你的任务是分析一组疑似相关的知识点之间的真实关系,
不是简单的"重复/不重复"二元判断,而是要识别它们的语义关系类型。

【六种关系类型,按重要性排序】

1. 🟢 cross_file_consensus(跨文件共识)— 多份不同政策文件反复重申同一政策
   触发条件:source_filename 不同 + 内容核心一致 + 时间跨度通常较短
   价值:这是国家或行业的高频共识政策,重要性极高,绝不能合并
   示例:2024 一号文件 + 2025 农业强国规划 都讲"健全联农带农益农机制"

2. 🔵 policy_evolution(政策演进)— 同一政策在不同时间的版本更迭
   触发条件:source_filename 不同 + 时间有先后 + 表述演化(细化/扩展/调整)
   价值:政策走向研判核心素材,投标方案的"政策延续性"论据
   示例:2024 提"探索建立",2025 升级为"健全...机制"

3. 🟣 hierarchical_refinement(细化关系)— 顶层政策 → 实施细则 → 落地方案
   触发条件:同主题但抽象层级不同(中央 → 部委 → 地方 / 原则 → 操作)
   价值:投标方案"从顶层到落地"完整证据链
   示例:中央"健全机制" + 农业农村部"实施意见" + 县级"操作手册"

4. 🟡 same_file_redundancy(同源冗余)— 同一文件不同段落讲同一件事
   触发条件:source_filename 相同 + 内容高度重叠
   价值:提取颗粒度问题,应合并保留信息量最大的一条
   示例:同一份白皮书第 3 段和第 28 段都讲"产业融合"

5. 🔴 conflicting(矛盾冲突)— 不同来源对同一问题给出矛盾结论
   触发条件:同主题但结论/数据/路径相反
   价值:政策研判的高价值发现,但需人工裁决
   示例:A 文件说"补贴应直达农户",B 文件说"应通过合作社"

6. ⚪ complementary(互补关系)— 同主题但角度互补,各有价值
   触发条件:同主题但视角不同(机制/落实/考核 / 主体方/监管方)
   价值:政策组合套餐生成的素材
   示例:A 讲"补贴机制",B 讲"补贴考核",C 讲"补贴预算"

7. ⚫ unrelated(无关)— 虽然标题/关键词相似,实际不是同一件事
   触发条件:核心主题/适用对象不同
   价值:不建关系,不需处理

【输入】
你将收到 N 条疑似相关的知识点,每条包含:
  - kp_id, title, content_type
  - 来源文件(关键判别依据!)
  - 入库时间(时间序判别)
  - 关键词, 内容摘要, 原文摘录(语义判别)

【输出严格 JSON,不要任何其他文字】
{
  "relation_type": "cross_file_consensus | policy_evolution | hierarchical_refinement | same_file_redundancy | conflicting | complementary | unrelated",
  "confidence": 0-100 整数 (你的判断置信度),
  "topic": "20 字内核心主题(用于聚类节点命名,unrelated 时留空)",
  "reason": "判断理由 50-150 字,要说出关键证据(看到了什么文件名差异/时间差/抽象层级差异)",
  "evidence_signals": {
    "source_diversity": "all_same | partial_same | all_different",
    "temporal_pattern": "no_time_info | same_period | clear_evolution",
    "abstraction_pattern": "same_level | hierarchical | mixed"
  },
  "cluster_suggestion": {
    "should_cluster": true | false,
    "core_kp_id": 建议作为 core 的 kp_id (信息量最大/最权威/最新),
    "member_roles": [
      {"kp_id": 数字, "role": "core|branch|derivative", "sequence_order": 演进链时填入0/1/2,其他类型填0}
    ]
  },
  "fallback_action": "keep_all | merge_to_core | human_review",
  "human_review_reason": "如 fallback_action=human_review,说明为什么不能 AI 决定;否则留空字符串"
}

【判定优先级 — 关键!】
1. 先看 source_filename:
   - 全部相同 → 优先 same_file_redundancy(should_cluster=false)
   - 不同 → 进入第 2 步
2. source_filename 不同时:
   - 看入库时间跨度 + 表述变化:跨期 + 演化明显 → policy_evolution
   - 同期 + 表述高度一致 → cross_file_consensus
   - 抽象层级有差异(中央 vs 地方 / 原则 vs 操作) → hierarchical_refinement
3. 看核心结论:
   - 有矛盾 → conflicting (fallback_action=human_review)
4. 都不像:
   - 视角互补 → complementary
   - 完全不相关 → unrelated

【cluster_suggestion 规则】
- 仅 cross_file_consensus / policy_evolution / hierarchical_refinement 三种关系建议建簇 (should_cluster=true)
- same_file_redundancy / conflicting / complementary / unrelated 不建簇 (should_cluster=false)
- core_kp_id 选择标准(优先级):内容最完整 > 来源最权威 > 时间最新 > excerpt 最长
- policy_evolution 的 sequence_order 必须按时间排序(0=最早,n-1=最新)

【重要原则】
- **默认倾向 cross_file_consensus 而非 same_file_redundancy**。
  理由:多份文件反复讲是政策的重要性信号,不是噪声。
- 不确定时 fallback_action: human_review,不要硬下结论。
- confidence 评分要诚实:依据充分给 80-95;依据不足给 30-65。
- 不要输出 JSON 以外的任何内容。""",
    "user_prompt_template": "{user_content}",
    "description": "知识关系六态判别(V3主+R1兜底,F2 v2.3.5-part1)"
}
