# 变更日志

## v2.0.0-b -- 变现底座：Prompt重写+提取引擎三层标签适配（阶段二）

发布日期：2026-03-23

变更内容：
- 5个提取Prompt全部重写，输出新增三层标签(category_tags/attribute_tags/keywords)+元数据(readiness/authority)
- 旧TAG_STRATEGY替换为THREE_LAYER_TAG_STRATEGY，标签清单从tag_config.py动态注入
- extractor.py解析三层标签并写入数据库新字段，旧suggested_tags不再填充
- 新增_sanitize_tags()校验AI返回的标签数据（过滤非法标签名、校验元数据值）
- TAG_SUGGESTION_PROMPT重写为三层标签版
- 新增QA_DERIVATION_PROMPT（待激活，v2.2.0启用）
- tag_config.py新增get_metadata_for_prompt()辅助函数
- AI分类建议prompt更新为感知三层标签体系
- 清理调试阶段不需要的迁移脚本

受影响文件：prompt_templates.py(重写), extractor.py(重写), tag_config.py(微调)
已删除文件：migrate_v101_to_v110.py, migrate_v110_to_v200.py, 数据库迁移_v200.bat
数据库迁移：不需要（调试阶段建议删库重建）
后续计划：v2.0.0-c(审核界面全面改版)

---

## v2.0.0-a -- 变现底座：数据库重构+三层标签配置（阶段一）

发布日期：2026-03-23

变更内容：
- 系统定位升级：从"知识整理工具"重构为"知识产品变现底座"
- 建立三层标签体系：第一层分类标签(6组41个)+第二层属性标签(8个维度)+第三层关键词(自由提取)
- 新增tag_config.py：标签定义独立配置文件，新增业务领域只改此文件，不改代码
- knowledge_points表新增11个字段：三层标签6个(suggested/final各3层)+元数据5个(就绪度/权威度/变现分级/保鲜时间/保鲜周期)
- 新增tag_definitions表：标签定义存储，从tag_config.py同步，供Prompt动态读取
- 新增knowledge_relations表：知识点关联关系（支撑/矛盾/同源/前置条件/更新替代）
- 新增knowledge_usage_log表：使用追踪，记录知识点被哪些产品引用
- 新增tag_statistics表：标签使用统计缓存
- 旧标签数据自动迁移至关键词字段
- 数据库从9张表扩展到13张表

受影响文件：db_manager.py(重写), tag_config.py(新增), migrate_v110_to_v200.py(新增), 数据库迁移_v200.bat(新增)
数据库迁移：需要（运行 数据库迁移_v200.bat）
后续计划：v2.0.0-b(Prompt重写+extractor改造) -> v2.0.0-c(审核界面改版)

---

## v1.1.0 -- 审核增强+分类管理+AI建议+全文搜索

发布日期：2026-03-20

变更内容：
- 树形分类筛选、全文搜索、编辑回滚+移除、忽略恢复
- 新增一级/二级分类、原文摘录和AI内容可编辑
- AI分类建议(新增/合并/重命名/拆分)、分类概览、置信度标记
- 标签质量过滤(去毒)、编辑历史追踪

受影响文件：extractor.py, api_server.py, db_manager.py, review.html, migrate_v101_to_v110.py
数据库迁移：需要

---

## v1.0.1 -- 提取引擎增强

发布日期：2026-03-19

变更内容：
- R1模型深度推理、5个Prompt强化、TAG_STRATEGY标签策略
- MD5去重、failed隔离、进度显示、R1适配

受影响文件：extractor.py, deepseek_client.py, prompt_templates.py, db_manager.py, api_server.py, review.html
数据库迁移：不需要

---

## v1.0.0 -- 核心版首次发布

发布日期：2026-03-18

变更内容：
- 核心工作流、10个脚本+11个bat+Flask审核界面
- SQLite 8张表+5种Prompt+API加密+费用保护+系统自检

受影响文件：全部
数据库迁移：不需要
