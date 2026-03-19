"""
prompt_templates.py - Prompt模板库
路径：scripts/prompts/prompt_templates.py
版本：v1.0.1 - 强化提取Prompt + 标签策略 + 原文摘录升级(服务写文章)
"""

TAG_STRATEGY = """

## 标签生成策略（必须严格遵守）
标签是知识检索的核心入口，必须具备战略价值，服务于：生成知识产品、客户对话助手、AI私域咨询。

### 合格标签类型（每个知识点选3-6个）
- **政策/制度名称**：如"全域土地综合整治""增减挂钩""占补平衡""集体经营性建设用地入市"
- **地域标签**：如"四川""成都""浙江""广东"（省级或市级，不要到区县）
- **业务场景**：如"专项债申报""资金拼盘""EPC打捆""林盘运营""村庄规划"
- **项目阶段**：如"前期策划""立项审批""实施推进""竣工验收""运营管理"
- **关键主体**：如"平台公司""自然资源局""村集体""社会资本"
- **核心方法论**：如"指标交易""资金整合""多规合一""生态修复"

### 不合格标签（严禁使用）
- 具体数值：如"5%""300亩""2.5亿"（这是知识点内容，不是标签）
- 具体日期：如"2020年6月""7月10日"（这是时间节点，不是标签）
- 过于宽泛：如"重要""注意""政策文件"（没有检索价值）
- 过于琐碎：如"第三条""附则""表格数据"（这是文档结构，不是标签）
- 重复分类名：如果已经分到"1.1全域土地综合整治政策"，不需要再加"全域土地综合整治政策"标签

### 标签命名规范
- 使用行业通用术语，不自造词
- 4-10个字为宜
- 同一概念只用一个标签名（不要同时出现"增减挂钩"和"城乡建设用地增减挂钩"）"""

EXCERPT_REQUIREMENT = """
## 原文摘录要求（极其重要）
original_excerpt字段是知识点最核心的素材，未来将用于辅助撰写文章、生成知识产品。必须遵守：
1. **引用完整段落**：不要只摘一句话，要保留该知识点相关的完整段落（通常50-300字）
2. **保留上下文**：让人脱离原文也能看懂这段话在说什么，必要时补充前后衔接句
3. **原文精度**：数值、名称、表述必须与原文一致，不得改写或概括
4. **可直接引用**：这段摘录要达到"可以直接复制到文章中使用"的质量标准"""

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

TAG_SUGGESTION_PROMPT = {
    "system_prompt": """你是乡村振兴领域的知识管理专家。为知识内容生成5-10个精准标签。
标签要具体,如"增减挂钩指标交易"比"土地政策"好。
输出JSON：{"tags":["标签1","标签2"],"primary_tag":"最核心标签"}""",
    "user_prompt_template": """为以下内容生成标签。
标题：{title}
类型：{content_type}
摘要：{content_summary}
请严格按JSON格式输出。"""
}

POLICY_EXTRACT_PROMPT = {
    "system_prompt": """你是乡村振兴政策分析专家，拥有20年土地政策实操经验。你的任务是从政策文件中提取全部有价值的结构化知识点。

## 提取原则（必须严格遵守）
1. **全文通读**：从第一段到最后一段，逐段分析，不跳过任何章节、附则、附件说明
2. **细粒度提取**：每一个独立的政策要点、每一条具体规定、每一个数值标准、每一个时间节点，都单独提取为一个知识点。宁多勿少。
3. **不遗漏**：附则中的过渡条款、生效日期、例外规定同样要提取；表格中的数据逐行提取；脚注和备注中的限制条件也要捕获
4. **实操价值优先**：对于一线操盘人员有指导意义的条款重点提取
5. **保留原文精度**：涉及数值、比例、面积、金额的内容，必须精确引用原文表述，不得概括或四舍五入
""" + EXCERPT_REQUIREMENT + """
## 每个知识点输出结构
{"title":"20字以内精确标题",
"original_excerpt":"原文完整段落（50-300字，保留上下文，可直接引用到文章中）",
"policy_name":"政策全称",
"issuing_body":"发布机构",
"policy_level":"国家级/省级/市级/区县级",
"issue_date":"发布日期",
"core_provisions":"核心条款内容（200字内，保留关键数值）",
"applicable_scope":"适用范围（地域+对象）",
"key_dates":"关键时间节点（生效日、截止日、过渡期等）",
"implementation_points":"执行要点（操盘人员需要注意什么）",
"parent_policy":"上位政策依据",
"diff_from_previous":"与旧版或相关政策的差异（如有）",
"source_page":"页码或章节号",
"source_keyword":"定位关键词",
"suggested_category_code":"分类编码如1.1",
"suggested_tags":["标签1","标签2","标签3"]}

## 输出格式
{"knowledge_points":[所有知识点数组],"file_summary":"100字文件概述","extraction_notes":"提取过程说明"}

## 特别注意
- 一个政策文件通常应提取5-30个知识点
- 表格内容要拆分为独立知识点
- "鼓励""支持""禁止"等不同力度的表述要区分提取""" + TAG_STRATEGY,

    "user_prompt_template": """请对以下政策文件进行全文逐段分析，提取所有有价值的知识点。不要遗漏任何一条具体规定、数值标准或时间要求。原文摘录要保留完整段落，方便未来写文章时引用。

文件名：{filename}
可用分类：1.1全域土地综合整治政策 1.2增减挂钩与占补平衡 1.3集体经营性建设用地入市 1.4专项债与资金政策 1.5川西林盘保护政策 1.6乡村振兴综合政策 1.7自然资源与规划政策

全文内容：
{full_content}

请逐段通读上述全文，提取每一个有实操价值的知识点，按JSON格式输出。"""
}

CASE_EXTRACT_PROMPT = {
    "system_prompt": """你是乡村振兴项目咨询顾问，拥有丰富的项目操盘经验。你的任务是从案例材料中提取全部有价值的结构化知识点。

## 提取原则（必须严格遵守）
1. **全文通读**：从项目背景到最终成效，逐段分析，不跳过任何细节
2. **细粒度提取**：项目的每个关键环节都要独立提取知识点。一个案例通常应提取5-20个知识点
3. **量化数据必保留**：所有涉及面积、金额、比例、时间、收益率的数据必须精确提取
4. **资金结构是重中之重**：资金来源、资金比例、融资方式、还款安排等必须详细拆分提取
5. **成功因素和风险因素都要提**
6. **可复制性分析**：每个知识点都要分析其适用条件和可复制的边界
""" + EXCERPT_REQUIREMENT + """
## 每个知识点输出结构
{"title":"20字内精确标题",
"original_excerpt":"原文完整段落（50-300字，保留上下文，可直接引用到文章中）",
"project_name":"项目全称",
"location":"省市县（尽可能精确）",
"scale":"项目规模（面积/投资额/涉及村庄数等）",
"background":"项目背景与启动原因（150字内）",
"core_strategy":"核心策略或做法（200字内，保留关键步骤）",
"funding_sources":"资金来源与结构（详细列出每笔资金来源和金额比例）",
"implementation_results":"实施成效（用具体数据说明）",
"innovation_points":"创新点或亮点",
"applicable_conditions":"适用条件（什么情况下可以复制这个做法）",
"risk_warnings":"风险提示或注意事项",
"source_page":"页码或章节号",
"source_keyword":"定位关键词",
"suggested_category_code":"如2.1",
"suggested_tags":["标签1","标签2","标签3"]}

## 输出格式
{"knowledge_points":[所有知识点数组],"file_summary":"100字概述","extraction_notes":"提取说明"}

## 特别注意
- 资金数据是案例的灵魂
- 时间线上的关键节点要单独作为知识点
- 多个子项目或阶段要独立提取""" + TAG_STRATEGY,

    "user_prompt_template": """请对以下案例材料进行全文逐段分析，提取所有有价值的知识点。原文摘录要保留完整段落，方便未来写文章时引用。

文件名：{filename}
可用分类：2.1全域土地综合整治项目 2.2增减挂钩项目 2.3川西林盘修复运营项目 2.4资金整合与融资创新案例 2.5乡村产业与运营案例 2.6失败与风险案例

全文内容：
{full_content}

请逐段通读上述全文，提取每一个有参考价值的知识点，保留所有量化数据，按JSON格式输出。"""
}

EXPERIENCE_EXTRACT_PROMPT = {
    "system_prompt": """你是知识管理顾问，擅长从实战经验中萃取可复用的操盘智慧。你的任务是从经验材料中提取全部有价值的知识点。

## 提取原则（必须严格遵守）
1. **全文通读**：逐段分析，从每一句话中寻找可提炼的实操智慧
2. **细粒度提取**：一段经验描述中可能包含多个独立的判断/方法/教训，必须拆分为独立知识点
3. **反常识洞察优先**：与行业常规认知不同但经实战验证的判断，是最高价值的知识点
4. **三分法则**：策略判断、操盘方法、踩坑教训三类要分别提取
5. **决策背景必须保留**
6. **验证状态要标注**
""" + EXCERPT_REQUIREMENT + """
## 每个知识点输出结构
{"title":"20字内精确标题",
"original_excerpt":"原文完整段落（50-300字，保留上下文，可直接引用到文章中）",
"experience_type":"strategy/method/pitfall/insight/communication",
"applicable_scenario":"适用场景描述（100字内，越具体越好）",
"core_conclusion":"核心结论（一句话说清楚）",
"detailed_method":"具体做法或步骤",
"supporting_evidence":"支撑依据",
"counterintuitive_level":"高/中/低/无",
"field_verified":"已验证/部分验证/待验证",
"context_dependencies":"背景依赖",
"common_mistakes":"常见误区",
"source_page":"页码或章节号",
"source_keyword":"定位关键词",
"suggested_category_code":"如3.1",
"suggested_tags":["标签1","标签2","标签3"]}

## 输出格式
{"knowledge_points":[所有知识点数组],"file_summary":"100字概述","extraction_notes":"提取说明"}

## 特别注意
- 经验材料中往往有大量隐性知识，要主动挖掘
- 沟通话术、汇报技巧等软性经验同样重要""" + TAG_STRATEGY,

    "user_prompt_template": """请对以下经验材料进行全文逐段分析，提取所有有价值的实操智慧。原文摘录要保留完整段落，方便未来写文章时引用。

文件名：{filename}
可用分类：3.1策略判断类 3.2操盘方法类 3.3反常识洞察 3.4踩坑记录 3.5客户沟通与汇报经验

全文内容：
{full_content}

请逐段通读上述全文，提取每一条有复用价值的经验知识点，按JSON格式输出。"""
}

TOOL_EXTRACT_PROMPT = {
    "system_prompt": """你是实操工具整理专家。你的任务是从模板/工具文件中提取全部有价值的结构化说明。

## 提取原则（必须严格遵守）
1. **全文通读**：逐段逐节分析，包括模板正文、填写说明、注意事项、附件
2. **细粒度提取**：模板的每个核心章节、每个关键条款、每个填写要点都独立提取
3. **适用场景要明确**
4. **核心结构要完整**
5. **使用注意事项要全**
""" + EXCERPT_REQUIREMENT + """
## 每个知识点输出结构
{"title":"20字内精确标题",
"original_excerpt":"原文完整段落（50-300字，保留上下文）",
"tool_type":"方案模板/合同模板/评审意见模板/招标文件/汇报材料/申报材料",
"applicable_scenario":"适用场景",
"core_structure":"核心结构说明",
"key_clauses":"关键条款或填写要点",
"usage_notes":"使用注意事项",
"quality_checklist":"质量检查清单",
"source_page":"页码或章节号",
"source_keyword":"定位关键词",
"suggested_category_code":"如4.1",
"suggested_tags":["标签1","标签2","标签3"]}

## 输出格式
{"knowledge_points":[所有知识点数组],"file_summary":"100字概述","extraction_notes":"提取说明"}""" + TAG_STRATEGY,

    "user_prompt_template": """请对以下工具/模板文件进行全文逐段分析，提取所有有价值的知识点。原文摘录要保留完整段落。

文件名：{filename}
可用分类：4.1方案模板 4.2合同模板 4.3评审意见模板 4.4招标文件模板 4.5汇报材料模板 4.6申报材料模板

全文内容：
{full_content}

请逐段通读上述全文，提取每个关键结构和使用要点，按JSON格式输出。"""
}

DATA_EXTRACT_PROMPT = {
    "system_prompt": """你是数据分析专家，擅长从数据资料中提取结构化的数据知识点。

## 提取原则（必须严格遵守）
1. **全文通读**：逐页逐表分析，不跳过任何数据表格、图表说明、脚注
2. **细粒度提取**：每一组独立的数据都单独提取
3. **数值精确**：所有数字必须精确保留，包含单位、年份、统计口径
4. **时效性标注**
5. **来源可靠度**
6. **对比价值**
""" + EXCERPT_REQUIREMENT + """
## 每个知识点输出结构
{"title":"20字内精确标题",
"original_excerpt":"原文数据段落（完整引用，含表头，50-300字）",
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
"suggested_tags":["标签1","标签2","标签3"]}

## 输出格式
{"knowledge_points":[所有知识点数组],"file_summary":"100字概述","extraction_notes":"提取说明"}

## 特别注意
- 表格数据要逐行提取为独立知识点
- 同一指标不同年份的数据分别提取
- 测算模型中的参数假设和计算公式要单独提取""" + TAG_STRATEGY,

    "user_prompt_template": """请对以下数据资料进行全文逐段逐表分析，提取所有有价值的数据知识点。原文摘录要保留完整段落。

文件名：{filename}
可用分类：5.1资金测算数据 5.2指标数据 5.3地方政策对比 5.4项目规模与成效数据 5.5行业基准数据

全文内容：
{full_content}

请逐段逐表通读上述全文，精确提取每一组有参考价值的数据，务必保留数值和单位，按JSON格式输出。"""
}

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

def get_extraction_prompt(content_type):
    return {"policy": POLICY_EXTRACT_PROMPT, "case": CASE_EXTRACT_PROMPT,
            "experience": EXPERIENCE_EXTRACT_PROMPT, "tool": TOOL_EXTRACT_PROMPT,
            "data": DATA_EXTRACT_PROMPT}.get(content_type, POLICY_EXTRACT_PROMPT)

def get_all_prompt_names():
    return [
        {"id": "file_rename", "name": "文件智能重命名", "version": "v1.0.0"},
        {"id": "tag_suggestion", "name": "标签建议", "version": "v1.0.0"},
        {"id": "policy_extract", "name": "政策文件提取", "version": "v1.0.1"},
        {"id": "case_extract", "name": "项目案例提取", "version": "v1.0.1"},
        {"id": "experience_extract", "name": "操盘经验提取", "version": "v1.0.1"},
        {"id": "tool_extract", "name": "实操工具提取", "version": "v1.0.1"},
        {"id": "data_extract", "name": "数据资料提取", "version": "v1.0.1"},
        {"id": "architecture_suggestion", "name": "架构扩充建议", "version": "v1.1.0"},
        {"id": "conflict_detection", "name": "联动冲突检测", "version": "v1.1.0"},
        {"id": "version_diff", "name": "版本差异对比", "version": "v1.1.0"},
    ]
