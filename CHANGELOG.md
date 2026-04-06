# 变更日志

## v2.1.2 第2批 -- 版本重提取+长任务支持+提取管理：F044+F047

发布日期：2026-04-06

变更内容：
- **F044 版本重提取**
  - api_server.py新增GET /api/tools/reextract-scan扫描旧版本知识点(按Prompt版本分组统计)
  - api_server.py新增POST /api/tasks/reextract版本重提取(自动备份→删除旧知识点→重置源文件状态→后台提取)
  - db_manager.py新增get_reextract_scan()按Prompt版本分组扫描
  - db_manager.py新增delete_kps_by_source_file()按源文件删除知识点(含操作日志)
  - review.html新增版本重提取面板(扫描→文件列表→勾选→执行)
- **F047 长任务后台执行**
  - api_server.py新增_task全局字典管理长任务状态(type/running/progress/steps/error/done)
  - api_server.py新增GET /api/tasks/progress长任务进度轮询
  - api_server.py新增POST /api/tasks/preprocess文件预处理(threading后台执行)
  - api_server.py新增POST /api/tasks/extract知识提取(threading后台执行+进度回调)
  - extractor.py新增progress_callback参数支持进度回调
  - extractor.py支持headless运行模式(无交互确认)
  - review.html新增长任务进度面板(进度条+步骤信息+完成/错误状态，2秒轮询)
- **提取管理**
  - review.html Tab 2新增提取管理区域(文件预处理/知识提取/版本重提取三个操作卡片)
  - 日常提取操作从bat文件迁移到管理后台

修改文件：api_server.py, db_manager.py, extractor.py, review.html

---

## v2.1.2 第1批 -- 管理后台框架+仪表盘+工具箱：F046+F033

发布日期：2026-04-05

变更内容：
- **F046+F033 管理后台框架+仪表盘+工具箱(交付A+B共4+1个文件)**
  - **交付A（后端API）：**
    - api_server.py新增GET /api/dashboard聚合仪表盘(9大数据板块一次返回)
    - api_server.py新增POST /api/tools/system-check系统检查(JSON输出)
    - api_server.py新增POST /api/tools/backup一键备份
    - api_server.py新增GET /api/tools/backup-list备份列表
    - api_server.py新增POST /api/tools/backup-restore恢复备份
    - api_server.py新增POST /api/tools/freshness-scan保鲜扫描
    - api_server.py新增POST /api/tools/duplicate-scan全库重复检测
    - api_server.py新增POST /api/tools/policy-revalidate政策补跑
    - api_server.py新增GET /api/tools/review-analytics审核统计(JSON输出)
    - api_server.py新增GET /api/tools/file-pipeline文件管线详情
    - api_server.py新增GET /api/tools/api-cost API费用详情(含7天趋势)
    - check_system.py升级至v2.5，新增run_checks_json()支持JSON输出
    - review_analytics.py新增get_analytics_json()支持JSON输出
    - 新增启动后台.bat替代原启动审核界面.bat
  - **交付B（前端UI）：**
    - review.html全面改版：Apple风格+Pantone 2026配色(Teal Green主色调)
    - 新增Tab框架：Tab 1知识审核(全部原有功能) | Tab 2系统管理
    - Tab 2仪表盘：9个数据卡片
    - Tab 2工具箱：8个操作按钮
    - CSS全面重构：毛玻璃Header、圆角14px卡片、柔和阴影、清新配色

新增文件：启动后台.bat
修改文件：api_server.py, check_system.py, review_analytics.py, review.html

---

## v2.1.1 第3批 -- 重复检测：F039

发布日期：2026-04-04

变更内容：
- **F039 轻量重复知识点检测(9个文件)**
  - 新增duplicate_checker.py重复检测核心模块(本地粗筛+V3精判)
  - 新增migrate_v211_dup.py迁移脚本(创建duplicate_groups表,第14张表)
  - 新增重复检测.bat(全库扫描入口)
  - 新增DUPLICATE_JUDGE_PROMPT(V3判断五种关系类型)
  - extractor.py新增Step 8增量重复检测
  - db_manager.py新增duplicate_groups表+5个CRUD方法
  - api_server.py新增3个重复检测端点
  - review.html新增重复检测提醒栏+处理面板
  - check_system.py升级至v2.4

新增文件：duplicate_checker.py, migrate_v211_dup.py, 重复检测.bat
修改文件：extractor.py, db_manager.py, api_server.py, review.html, check_system.py, prompt_templates.py

---

## v2.1.1 第2批 -- 举一反三提取增强：F038

发布日期：2026-04-03

变更内容：
- **F038 举一反三提取增强(7个文件)**
  - 新增migrate_v211.py迁移脚本
  - prompt_templates.py: 新增PRACTICAL_INSIGHTS_INSTRUCTION+QC扩展6维度
  - extractor.py/db_manager.py/api_server.py/review.html/check_system.py同步更新

新增文件：migrate_v211.py
修改文件：prompt_templates.py, extractor.py, db_manager.py, api_server.py, review.html, check_system.py

---

## v2.1.1 第1批 -- bat文件修复+审核界面Bug修复：F040+F041

发布日期：2026-04-03

---

## v2.1.0-d 第2批 -- 政策依赖校验前端：F028审核界面+系统检查

发布日期：2026-03-29

---

## v2.1.0-d 第1.5批 -- 政策依赖校验后端：F028核心模块

发布日期：2026-03-29

---

## v2.1.0-d 第1批 -- 保鲜提醒：F015内容保鲜提醒

发布日期：2026-03-28

---

## v2.1.0-c 第4批 -- 提取质量加固：系统检查升级

发布日期：2026-03-28

---

## v2.1.0-c 第3批 -- 提取质量加固：V3质检+审核反馈统计

发布日期：2026-03-27

---

## v2.1.0-c 第1-2批 -- 提取质量加固：Prompt重写+智能分段+预分析

发布日期：2026-03-27

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
