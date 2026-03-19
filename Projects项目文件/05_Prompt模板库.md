# Prompt模板库
> 最后更新：v1.0.1
> 完整代码：scripts/prompts/prompt_templates.py

## 清单

| 序号 | 变量名 | 中文名 | 状态 |
|------|--------|--------|------|
| 1 | FILE_RENAME_PROMPT | 文件智能重命名 | 生效(v1.0.0) |
| 2 | TAG_SUGGESTION_PROMPT | 标签建议 | 生效(v1.0.0) |
| 3 | POLICY_EXTRACT_PROMPT | 政策文件提取 | 生效(v1.0.1强化) |
| 4 | CASE_EXTRACT_PROMPT | 项目案例提取 | 生效(v1.0.1强化) |
| 5 | EXPERIENCE_EXTRACT_PROMPT | 操盘经验提取 | 生效(v1.0.1强化) |
| 6 | TOOL_EXTRACT_PROMPT | 实操工具提取 | 生效(v1.0.1强化) |
| 7 | DATA_EXTRACT_PROMPT | 数据资料提取 | 生效(v1.0.1强化) |
| 8 | ARCHITECTURE_SUGGESTION_PROMPT | 架构扩充建议 | v1.1.0待激活 |
| 9 | CONFLICT_DETECTION_PROMPT | 联动冲突检测 | v1.1.0待激活 |
| 10 | VERSION_DIFF_PROMPT | 版本差异对比 | v1.1.0待激活 |

## 核心策略

### v1.0.1 强化要点（适配R1深度推理模型）
- 所有提取Prompt增加"全文逐段通读、不跳过任何章节"硬性要求
- 增加颗粒度基准线（如政策文件通常应提取5-30个知识点）
- 要求表格数据逐行提取为独立知识点
- 要求保留原文精度，数值不得概括或四舍五入

### 各模板策略
- FILE_RENAME: [年份][类型]_[主题]_[来源] -> JSON
- POLICY_EXTRACT: 核心条款+执行要点+时间节点, 实操价值优先, 附则/表格/脚注不遗漏
- CASE_EXTRACT: 量化数据必保留, 资金结构是核心, 时间线关键节点独立提取, 可复制性分析
- EXPERIENCE_EXTRACT: 反常识+决策背景+策略/方法/踩坑三分, 隐性知识挖掘, 常见误区字段
- TOOL_EXTRACT: 适用场景+核心结构+关键条款+使用注意事项+质量检查清单
- DATA_EXTRACT: 数值精确含单位, 标注时效性和可靠度, 表格逐行提取, 对比说明字段

## 修改历史
| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-03-19 | v1.0.1 | 5个提取Prompt全面强化，适配R1模型深度推理 |
