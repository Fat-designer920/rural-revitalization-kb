# 变更日志

## v2.1.0-d 第2批 -- 政策依赖校验前端：F028审核界面+系统检查

发布日期：2026-03-29

变更内容：
- migrate_v210d.py新增policy_dependencies和policy_validated字段迁移
- db_manager.py新增get_policy_validation_summary()政策校验状态摘要
- db_manager.py的get_all_knowledge_points新增policy_filter参数支持
- api_server.py新增3个政策校验端点：摘要/人工豁免/重新校验
- api_server.py新增policy筛选参数支持
- api_server.py的_safe()新增policy_dependencies JSON解析
- review.html新增政策校验徽标(已验证/待验证/已豁免/未校验)
- review.html新增待验证知识点政策依赖详情展开(未匹配政策+查找指引)
- review.html新增侧边栏政策校验筛选(全部/待验证/已验证/已豁免/未校验/不涉及)
- review.html新增豁免校验+重新校验按钮
- review.html新增编辑弹窗政策依赖只读展示
- check_system.py升级至v2.2，新增第14项政策校验状态检查
- check_system.py迁移检查扩展policy_dependencies+policy_validated
- 新增政策补跑.bat(对历史知识点补跑政策校验)

新增文件：政策补跑.bat
修改文件：migrate_v210d.py, db_manager.py, api_server.py, review.html, check_system.py
数据库迁移：migrate_v210d.py(knowledge_points+policy_dependencies+policy_validated)

---

## v2.1.0-d 第1.5批 -- 政策依赖校验后端：F028核心模块

发布日期：2026-03-29

变更内容：
- 新增policy_validator.py政策依赖校验模块(V3扫描+KB匹配+就绪度锁定)
- extractor.py新增Step 7政策依赖校验集成
- prompt_templates.py新增POLICY_SCAN_PROMPT(V3扫描政策引用)
- tag_config.py新增POLICY_LOOKUP_GUIDE(政策查找指引模板)
- db_manager.py的update_knowledge_point允许policy_dependencies/policy_validated

新增文件：policy_validator.py
修改文件：extractor.py, prompt_templates.py, tag_config.py, db_manager.py

---

## v2.1.0-d 第1批 -- 保鲜提醒：F015内容保鲜提醒

发布日期：2026-03-28

变更内容：
- 新增freshness_checker.py保鲜扫描脚本(扫描+分组报告+自动补默认周期)
- 新增migrate_v210d.py迁移脚本(knowledge_points加freshness_note字段)
- tag_config.py新增FRESHNESS_INTERVALS保鲜周期配置(政策90天/案例180天/经验365天/工具365天/数据90天)
- db_manager.py新增保鲜方法：get_freshness_summary/renew_freshness/mark_knowledge_outdated
- db_manager.py的get_all_knowledge_points新增freshness_filter参数支持
- api_server.py新增4个保鲜端点：摘要/续期/批量续期/标记过时
- review.html新增保鲜提醒栏+保鲜徽标+保鲜筛选+续期+批量续期+已过时灰显
- check_system.py升级至v2.1，新增第13项保鲜状态检查
- 新增保鲜检查.bat

---

## v2.1.0-c 第4批 -- 提取质量加固：系统检查升级

发布日期：2026-03-28

变更内容：
- check_system.py从v1.0升级到v2.0，从6项检查扩展到12项

---

## v2.1.0-c 第3批 -- 提取质量加固：V3质检+审核反馈统计

发布日期：2026-03-27

变更内容：
- extractor.py新增V3质检(Step 6)
- api_server.py新增sort_by_qa参数支持
- review.html新增质检分数徽标和质检排序
- 新增review_analytics.py审核反馈统计脚本+审核统计.bat

---

## v2.1.0-c 第1-2批 -- 提取质量加固：Prompt重写+智能分段+预分析

发布日期：2026-03-27

变更内容：
- 第1批：prompt_templates.py深度重写(893行,15个Prompt)
- 第2批：extractor.py重大改造(1035行)+migrate_v210c.py+一键提取.bat

---

## v2.1.0-b -- 安全网：知识库架构升级迁移（阶段二）
发布日期：2026-03-25

---

## v2.1.0-a -- 安全网：备份恢复（阶段一）
发布日期：2026-03-25

---

## v2.0.0-c -- 变现底座：审核界面全面改版（阶段三）
发布日期：2026-03-23

---

## v2.0.0-b -- 变现底座：Prompt重写+提取引擎三层标签适配（阶段二）
发布日期：2026-03-23

---

## v2.0.0-a -- 变现底座：数据库重构+三层标签配置（阶段一）
发布日期：2026-03-23

---

## v1.1.0 -- 审核增强+分类管理+AI建议+全文搜索
发布日期：2026-03-20

---

## v1.0.1 -- 提取引擎增强
发布日期：2026-03-19

---

## v1.0.0 -- 核心版首次发布
发布日期：2026-03-18
