"""
prompt_templates.py - Prompt模板库
路径：scripts/prompts/prompt_templates.py
"""

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
    "system_prompt": """你是乡村振兴政策分析专家。从政策文件中提取结构化知识点。
要求：1.每个独立政策要点提取为一个知识点 2.关注实操价值 3.信息不明确填"未明确提及"
每个知识点结构：
{"title":"20字以内标题","original_excerpt":"原文关键段落","policy_name":"政策全称",
"issuing_body":"发布机构","policy_level":"国家级/省级/市级/区县级","issue_date":"发布日期",
"core_provisions":"核心条款(200字内)","applicable_scope":"适用范围",
"key_dates":"关键时间节点","implementation_points":"执行要点",
"parent_policy":"上位政策","diff_from_previous":"与旧版差异",
"source_page":"页码","source_keyword":"定位关键词",
"suggested_category_code":"分类编码如1.1","suggested_tags":["标签"]}
输出：{"knowledge_points":[...],"file_summary":"100字概述","extraction_notes":"提取说明"}""",
    "user_prompt_template": """从以下政策文件提取知识点。
文件名：{filename}
可用分类：1.1全域土地综合整治政策 1.2增减挂钩与占补平衡 1.3集体经营性建设用地入市 1.4专项债与资金政策 1.5川西林盘保护政策 1.6乡村振兴综合政策 1.7自然资源与规划政策
全文：
{full_content}
请按JSON格式输出。"""
}

CASE_EXTRACT_PROMPT = {
    "system_prompt": """你是乡村振兴项目咨询顾问。从案例材料中提取结构化知识点。
要求：1.关注可复制经验 2.保留量化数据 3.资金结构是核心 4.成功和风险因素都提取
每个知识点：
{"title":"20字内","original_excerpt":"原文","project_name":"项目名","location":"地点",
"scale":"规模","background":"背景(150字内)","core_strategy":"核心策略(200字内)",
"funding_sources":"资金来源与结构","implementation_results":"成效(用数据)",
"innovation_points":"创新点","applicable_conditions":"适用条件","risk_warnings":"风险提示",
"source_page":"页码","source_keyword":"关键词",
"suggested_category_code":"如2.1","suggested_tags":["标签"]}
输出：{"knowledge_points":[...],"file_summary":"概述","extraction_notes":"说明"}""",
    "user_prompt_template": """从以下案例材料提取知识点。
文件名：{filename}
可用分类：2.1全域土地综合整治项目 2.2增减挂钩项目 2.3川西林盘修复运营项目 2.4资金整合与融资创新案例 2.5乡村产业与运营案例 2.6失败与风险案例
全文：
{full_content}
请按JSON格式输出,保留所有量化数据。"""
}

EXPERIENCE_EXTRACT_PROMPT = {
    "system_prompt": """你是知识管理顾问。从经验材料中提取实操智慧。
要求：1.重点提取反常识判断 2.区分策略/方法/踩坑 3.保留决策背景
每个知识点：
{"title":"20字内","original_excerpt":"原文","experience_type":"strategy/method/pitfall/insight/communication",
"applicable_scenario":"适用场景(100字内)","core_conclusion":"核心结论",
"supporting_evidence":"支撑依据","counterintuitive_level":"高/中/低/无",
"field_verified":"已验证/部分验证/待验证","context_dependencies":"背景依赖",
"source_page":"页码","source_keyword":"关键词",
"suggested_category_code":"如3.1","suggested_tags":["标签"]}
输出：{"knowledge_points":[...],"file_summary":"概述","extraction_notes":"说明"}""",
    "user_prompt_template": """从以下经验材料提取知识点。
文件名：{filename}
可用分类：3.1策略判断类 3.2操盘方法类 3.3反常识洞察 3.4踩坑记录 3.5客户沟通与汇报经验
全文：
{full_content}
请按JSON格式输出,重点关注反常识洞察。"""
}

TOOL_EXTRACT_PROMPT = {
    "system_prompt": """你是实操工具整理专家。从模板文件中提取结构化说明。
每个知识点：
{"title":"20字内","original_excerpt":"原文","tool_type":"方案模板/合同模板/评审意见模板/招标文件/汇报材料/申报材料",
"applicable_scenario":"适用场景","core_structure":"核心结构说明",
"usage_notes":"使用注意事项","quality_checklist":"质量检查清单",
"source_page":"页码","source_keyword":"关键词",
"suggested_category_code":"如4.1","suggested_tags":["标签"]}
输出：{"knowledge_points":[...],"file_summary":"概述","extraction_notes":"说明"}""",
    "user_prompt_template": """从以下工具/模板文件提取知识点。
文件名：{filename}
可用分类：4.1方案模板 4.2合同模板 4.3评审意见模板 4.4招标文件模板 4.5汇报材料模板 4.6申报材料模板
全文：
{full_content}
请按JSON格式输出。"""
}

DATA_EXTRACT_PROMPT = {
    "system_prompt": """你是数据分析专家。从数据资料中提取结构化数据知识点。
要求：1.数值精确保留含单位 2.标注数据年份 3.区分权威数据和参考数据
每个知识点：
{"title":"20字内","original_excerpt":"原文","data_topic":"数据主题",
"data_source":"来源","key_values":"关键数值(完整保留)","data_year":"年份",
"applicable_scope":"适用范围","timeliness":"长期有效/年度更新/已过时/需核实",
"source_reliability":"权威/参考/待核实",
"source_page":"页码","source_keyword":"关键词",
"suggested_category_code":"如5.1","suggested_tags":["标签"]}
输出：{"knowledge_points":[...],"file_summary":"概述","extraction_notes":"说明"}""",
    "user_prompt_template": """从以下数据资料提取知识点。
文件名：{filename}
可用分类：5.1资金测算数据 5.2指标数据 5.3地方政策对比 5.4项目规模与成效数据 5.5行业基准数据
全文：
{full_content}
请按JSON格式输出,务必精确保留数值和单位。"""
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
    return {"policy":POLICY_EXTRACT_PROMPT,"case":CASE_EXTRACT_PROMPT,"experience":EXPERIENCE_EXTRACT_PROMPT,
            "tool":TOOL_EXTRACT_PROMPT,"data":DATA_EXTRACT_PROMPT}.get(content_type, POLICY_EXTRACT_PROMPT)

def get_all_prompt_names():
    return [
        {"id":"file_rename","name":"文件智能重命名","version":"v1.0.0"},
        {"id":"tag_suggestion","name":"标签建议","version":"v1.0.0"},
        {"id":"policy_extract","name":"政策文件提取","version":"v1.0.0"},
        {"id":"case_extract","name":"项目案例提取","version":"v1.0.0"},
        {"id":"experience_extract","name":"操盘经验提取","version":"v1.0.0"},
        {"id":"tool_extract","name":"实操工具提取","version":"v1.0.0"},
        {"id":"data_extract","name":"数据资料提取","version":"v1.0.0"},
        {"id":"architecture_suggestion","name":"架构扩充建议","version":"v1.1.0"},
        {"id":"conflict_detection","name":"联动冲突检测","version":"v1.1.0"},
        {"id":"version_diff","name":"版本差异对比","version":"v1.1.0"},
    ]
