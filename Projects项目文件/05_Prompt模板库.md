# Prompt模板库
> 最后更新：v2.0.0-b（5个提取Prompt已重写，三层标签适配完成）
> 完整代码：scripts/prompts/prompt_templates.py

## 清单

| 序号 | 变量名 | 中文名 | 状态 |
|------|--------|--------|------|
| 1 | FILE_RENAME_PROMPT | 文件智能重命名 | 生效(v1.0.0) |
| 2 | TAG_SUGGESTION_PROMPT | 标签建议(三层标签版) | 生效(v2.0.0) |
| 3 | POLICY_EXTRACT_PROMPT | 政策文件提取(三层标签版) | **生效(v2.0.0)** |
| 4 | CASE_EXTRACT_PROMPT | 项目案例提取(三层标签版) | **生效(v2.0.0)** |
| 5 | EXPERIENCE_EXTRACT_PROMPT | 操盘经验提取(三层标签版) | **生效(v2.0.0)** |
| 6 | TOOL_EXTRACT_PROMPT | 实操工具提取(三层标签版) | **生效(v2.0.0)** |
| 7 | DATA_EXTRACT_PROMPT | 数据资料提取(三层标签版) | **生效(v2.0.0)** |
| 8 | ARCHITECTURE_SUGGESTION_PROMPT | 架构扩充建议 | 生效(v1.1.0) |
| 9 | CONFLICT_DETECTION_PROMPT | 联动冲突检测 | 待激活 |
| 10 | VERSION_DIFF_PROMPT | 版本差异对比 | 待激活 |
| 11 | QA_DERIVATION_PROMPT | 问答语料衍生 | **待激活(v2.0.0新增,v2.2.0启用)** |

## v2.0.0-b 重写完成

### 输出格式变更（已实施）
每个提取Prompt的输出JSON新增以下字段：
- suggested_category_tags: 从41个固定标签中选3-6个（标签名称，非编号）
- suggested_attribute_tags: 按维度填写属性值（JSON对象，key=维度英文名）
- suggested_keywords: 自由提取5-15个关键词
- suggested_readiness: 就绪度建议(draft/quotable/premium)
- suggested_authority: 来源权威度建议(official/authoritative/firsthand/informal)

### 标签注入机制（已实施）
- get_extraction_prompt(content_type)调用时自动从tag_config.py读取标签清单
- 标签清单拼接为{tag_reference}注入到user_prompt中
- 包含：第一层标签完整清单 + 第二层属性维度(按content_type过滤) + 第三层关键词规则 + 元数据判断参考
- 新增业务领域只需改tag_config.py的A组，Prompt自动适配

### 通用策略块
- THREE_LAYER_TAG_STRATEGY: 替代旧的TAG_STRATEGY，指导AI进行三层标签打标
- COMMON_TAG_OUTPUT_DESC: 三层标签+元数据的JSON字段描述，各Prompt共享
- EXCERPT_REQUIREMENT: 原文摘录要求（不变）

### 核心策略（v1.0.1保留）
- EXCERPT_REQUIREMENT原文摘录要求(不变)
- 全文逐段通读/颗粒度基准线/表格逐行提取/原文精度(不变)
- 旧TAG_STRATEGY已删除，由THREE_LAYER_TAG_STRATEGY替代

## 修改历史
| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-03-23 | v2.0.0-b | 5个提取Prompt重写(三层标签输出)，TAG_SUGGESTION重写，新增QA_DERIVATION_PROMPT |
| 2026-03-23 | v2.0.0-a | 标签体系定义完成(tag_config.py),Prompt待下一阶段重写 |
| 2026-03-19 | v1.0.1 | 5个提取Prompt强化,新增TAG_STRATEGY和EXCERPT_REQUIREMENT |
