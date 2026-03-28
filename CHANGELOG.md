# 变更日志

## v2.1.0-d 第1批 -- 保鲜提醒：F015内容保鲜提醒

发布日期：2026-03-28

变更内容：
- 新增freshness_checker.py保鲜扫描脚本(扫描+分组报告+自动补默认周期)
- 新增migrate_v210d.py迁移脚本(knowledge_points加freshness_note字段)
- tag_config.py新增FRESHNESS_INTERVALS保鲜周期配置(政策90天/案例180天/经验365天/工具365天/数据90天)
- db_manager.py新增保鲜方法：get_freshness_summary/renew_freshness/mark_knowledge_outdated
- db_manager.py的get_all_knowledge_points新增freshness_filter参数支持
- api_server.py新增4个保鲜端点：摘要/续期/批量续期/标记过时
- api_server.py的PUT新增freshness_interval_days/freshness_note字段支持，编辑内容自动刷新保鲜时间
- api_server.py的tag-definitions新增返回FRESHNESS_INTERVALS
- review.html新增保鲜提醒栏(顶部橙色提示,过期/即将到期数量)
- review.html新增保鲜状态徽标(新鲜/即将到期/已过期/已过时)
- review.html新增保鲜筛选(侧边栏保鲜状态过滤)
- review.html新增续期操作(确认仍有效/标记过时,支持写备注)
- review.html新增批量续期按钮
- review.html编辑弹窗增加保鲜周期和保鲜备注编辑
- review.html已过时知识点灰显(card-outdated样式)
- check_system.py升级至v2.1，新增第13项保鲜状态检查
- check_system.py新增v2.1.0-d迁移字段检查(freshness_note)
- 新增保鲜检查.bat
- 版本号统一更新至v2.1.0-d

新增文件：freshness_checker.py, migrate_v210d.py, 保鲜检查.bat
修改文件：tag_config.py, db_manager.py, api_server.py, review.html, check_system.py
数据库迁移：migrate_v210d.py(knowledge_points+freshness_note)

---

## v2.1.0-c 第4批 -- 提取质量加固：系统检查升级

发布日期：2026-03-28

变更内容：
- check_system.py从v1.0升级到v2.0，从6项检查扩展到12项
- 新增数据库迁移状态检查（v2.1.0-c的6个新字段是否存在）
- 新增知识库健康度概览（状态/类型/就绪度分布+源文件统计）
- 新增Prompt版本检查（统计旧版本知识点数量，提示升级路径）
- 新增V3质检覆盖率（已检/未检/平均分/低分预警）
- 新增备份状态检查（最近备份时间/数量）
- 新增文件管线状态（pending/processing/completed/failed文件数+行动建议）
- v2.1.0-c全部4批交付完毕

修改文件：check_system.py(重写)
数据库迁移：不需要

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
