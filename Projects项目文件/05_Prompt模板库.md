# Prompt模板库
> 最后更新：v1.0.0
> 完整代码：scripts/prompts/prompt_templates.py

## 清单

| 序号 | 变量名 | 中文名 | 状态 |
|------|--------|--------|------|
| 1 | FILE_RENAME_PROMPT | 文件智能重命名 | 生效 |
| 2 | TAG_SUGGESTION_PROMPT | 标签建议 | 生效 |
| 3 | POLICY_EXTRACT_PROMPT | 政策文件提取 | 生效 |
| 4 | CASE_EXTRACT_PROMPT | 项目案例提取 | 生效 |
| 5 | EXPERIENCE_EXTRACT_PROMPT | 操盘经验提取 | 生效 |
| 6 | TOOL_EXTRACT_PROMPT | 实操工具提取 | 生效 |
| 7 | DATA_EXTRACT_PROMPT | 数据资料提取 | 生效 |
| 8 | ARCHITECTURE_SUGGESTION_PROMPT | 架构扩充建议 | v1.1.0待激活 |
| 9 | CONFLICT_DETECTION_PROMPT | 联动冲突检测 | v1.1.0待激活 |
| 10 | VERSION_DIFF_PROMPT | 版本差异对比 | v1.1.0待激活 |

## 核心策略
- FILE_RENAME: [年份][类型]_[主题]_[来源] -> JSON
- POLICY_EXTRACT: 核心条款+执行要点+时间节点, 实操价值优先
- CASE_EXTRACT: 量化数据必保留, 资金结构是核心
- EXPERIENCE_EXTRACT: 反常识+决策背景+策略/方法/踩坑三分
- TOOL_EXTRACT: 适用场景+核心结构+使用注意事项
- DATA_EXTRACT: 数值精确含单位, 标注时效性和可靠度

## 修改历史
（初始为空）
