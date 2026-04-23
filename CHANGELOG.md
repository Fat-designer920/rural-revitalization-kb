# CHANGELOG

> 乡村振兴知识库搭建助手 — 版本变更记录
>
> 格式：近 3 版完整 Added / Fixed / Changed / Migration 四段式。早期版本折叠为一行摘要，完整历史见 [GitHub Releases](https://github.com/Fat-designer920/rural-revitalization-kb/releases)。

---

## [v2.3.0-part3] - 2026-04-24

**定位**：F062 端到端健康测试 Agent 三对话拆分 —— 对话 3/3 界面层正式版（全闭环）

### Added

- **`scripts/api_server.py`**（+422 行，2834 → 3256）：F062 界面后端
  - 7 个路由：`/e2e/latest` / `/start` / `/history` / `/report/<rid>` / `/issues` / `/issues/<iid>/status`
  - 2 个辅助函数：`_e2e_readiness_check` 启动 4 项自检（放 `_task_lock` 之前）+ `_e2e_progress_adapter` 9 stage 映射
  - `_task["type"]="e2e"` 前后端锁定
- **`web/templates/review.html`**（+458 行，2692 → 3150）：F062 界面前端
  - 工具箱第 11 张卡 `tc-e2e`（青蓝 E #E6F3FB/#1F7AAC）+ 软提醒徽章（≤7 天无 / 7-14 天淡黄 / >14 天红）
  - 3 个模态框：档位二选一 / 报告详情（六维度 2×3 卡）/ issue 左右分栏（五 tab + 四态按钮）
  - 新增 9 JS 函数（严格 ES5）+ 2 状态变量 + CSS ~70 行
- **`scripts/db_manager.py`**（+26 行）：破例补齐 `get_e2e_test_report_list`（对称 F048 `get_health_report_list`），F062 方法从 8 → 9
- **`scripts/setup.py`**：核心文件清单追加 `static_analyzer.py` + `e2e_tester.py`
- **`scripts/check_system.py`**（v2.5.1 → v2.5.2）：[4] 表清单扩到 12 张 + 新增 [19] F062 就绪度（4 小项）
- **`scripts/db_health_check.py`**（v1.1 → v1.2）：EXPECTED_TABLES +3 + 新增 [12/12] F062 代码层契约（6 小项）

### Fixed

无 bug 修复。本次为对话 3/3 正常交付。

### Changed

- 项目文件全量更新：00 / 01 / 03 / README / CHANGELOG

### Migration

**无 schema 变更**。对话 1 已落地的 3 张 F062 表在本次被界面层消费，零改动。

### Upgrade Path

1. 备份数据库
2. 替换 6 个代码文件：`api_server.py` / `review.html` / `db_manager.py` / `setup.py` / `check_system.py` / `db_health_check.py`
3. 推送 GitHub（Summary: `v2.3.0-part3: F062 界面层正式版 全闭环`）
4. 重启服务 + 浏览器 Ctrl+F5

---

## [v2.3.0-part2.2] - 2026-04-22 (hotfix)

**定位**：F048 防护层 —— 四类系统性 bug 修复 + 启动就绪性自检

### Added

- **`_health_readiness_check()`**：4 层自检模板（Prompt / DB / client / schema 字段契约），放 `_task_lock` 之前执行
- **db_manager 三扫描查询 LEFT JOIN categories**：`get_kp_for_health_scan / get_polish_candidates / get_island_candidates` 追加 `LEFT JOIN categories c ON c.id = kp.final_category_id` + AS 映射 `category / subcategory`

### Fixed（四类系统性 bug，实测截图 47.16 分拆解）

1. **Prompt 未落地**：prompt_templates.py 补齐 6 个 F048 Prompt 正式版文本 + PROMPT_VERSION 升版
2. **import 静默降级**：health_checker.py 所有 `HEALTH_*_PROMPT` 改顶层 `from ... import`，删除 try/except fallback 和 6 处 `if not PROMPT: return None` 防御分支
3. **字段读取 bug**：db 层 JOIN categories 后 AS 映射 `category` / `subcategory`，health_checker 读到真值
4. **Prompt key 错配**（实测发现）：6 处 `['system']` → `['system_prompt']`，6 处 `['user']` → `['user_prompt_template']`

### Changed

- `_task["type"]` 口径全面校正为 `"health"`（原项目文件曾误标为 `"health_check"`，以代码为准）
- `_dim2_structure_score` detail 补"未分类 kp 数"（`final_category_id IS NULL` 计数）

### Migration

无 schema 变更。

### 立规则（写入 01 工程手册）

1. schema 单一来源原则
2. 禁止"包级静默降级"
3. 文档契约字段名必须从 schema 源文件取真相
4. 长任务启动就绪性自检必须在 `_task_lock` 之前
5. 三件套隐藏 bug：懒加载 + None 兜底 + 字段读取，只改前两件必暴露第三件

---

## [v2.3.0-part2] - 2026-04-22

**定位**：F048 知识库体检 Agent 三对话拆分全闭环（基础层 + 引擎层 + 界面层）

### Added

- **`prompt_templates.py`**：6 个 F048 Prompt 契约 + PROMPT_VERSION v2.2.3 → v2.3.0-part2
- **`db_manager.py`**：+2 张表（health_reports / polish_suggestions）+ 3 索引 + 12 个方法（5 读写 + 4 打磨 + 3 扫描候选）
- **`health_checker.py`**（新建 ~1360 行）：F048 引擎核心
  - 六维度扫描（`_safe_dim` 单维度异常隔离）
  - 三层打磨降级链（V3 诊断 → R1 打磨 → V3 校验 → L2 保守 → L3 规则兜底）
  - 孤岛精判（抽样外推，ISLAND_JUDGE_MAX_COUNT=50）
  - 变现报告（5 场景评分 + overall_monetize_score）
  - V3 调用五方法两签名适配器
  - 9 stage progress_callback + 10 种 operation_events 埋点
- **`api_server.py`**：+8 F048 路由 + `_health_progress_adapter`（total_files=8）
- **`review.html`**（+603 行）：工具箱第 10 卡 `tc-health`（紫 H）+ 3 模态框（档位 / 报告 / Review）+ 13 JS 函数 + `_renderReviewSide` 辅助 + CSS ~85 行
- **operation_hook("health_adopt")**：6 个关键备份触发点第 6 个正式接入

### Fixed

- v2.1.2 分批质检内层循环 bug（v2.2.3 已顺手修，此版本不再相关）

### Changed

- 工具箱卡 9 → 10（part3 F062 才到 11）
- `_task["type"]="health"`（代码实装口径）
- `suggestion_type` 徽章六色：drop 红 / split 蓝 / improve 紫 / manual 灰 / enrich 青 / merge 橙
- 按钮矩阵 4 分支严格对齐 tier × suggestion_type

### Migration

```sql
CREATE TABLE health_reports (...);
CREATE INDEX idx_health_created ON health_reports(created_at DESC);
CREATE TABLE polish_suggestions (...);
CREATE INDEX idx_polish_report ON polish_suggestions(report_id);
CREATE INDEX idx_polish_status ON polish_suggestions(status);
```

（v2.3.0-part2.1 hotfix 已将两表吸收进 `init_tables`，migrate 脚本退役）

### 关键设计决策

1. `_merge_ai_content` 固定 8 条映射（不按 content_type 分流）
2. split 采纳只取 `sc[0]` + split_note 提示手动
3. drop 独立路由 + op_name 复用 `"health_adopt"`
4. content_readiness 采纳后不动
5. /latest 瘦身返回 + /report/<rid> 完整
6. 本地 splice 不重新请求
7. 略过纯前端指针移动

---

## 早期版本精简摘要

### v2.3.0-part3-alpha2 — 2026-04-23 (alpha)

F062 对话 2/3 引擎层 `e2e_tester.py`（~1250 行）新建。六维度扫描 + V3 调用五方法两签名适配器 + 白名单二次过滤（dim4 35 + dim6 6 = 41 unique signature）+ 9 stage progress_callback + 16 种 operation_events 埋点。dry run 验证通过。

### v2.3.0-part3-alpha1 — 2026-04-23 (alpha)

F062 对话 1/3 基础层：prompt_templates（+E2E_RESPONSE_JUDGE_PROMPT + PROMPT_VERSION 升版）+ db_manager（+3 表 api_endpoint_registry / e2e_test_reports / e2e_issues + 3 索引 + 8 方法）+ static_analyzer.py（新建 645 行，维度③④⑥ AST 规则库）。SQLite 表总数 18 → 21。立规则 6 条（severity 严格三态 / 四态 CHECK 强约束 / 偶发升级内置 upsert / fixed 回归检测 / static_analyzer 宁可多告警 / endpoint TEXT PRIMARY KEY）。

### v2.3.0-part2.1 — 2026-04-22 (hotfix)

schema 单一来源修复：`init_tables()` 吸收 health_reports / polish_suggestions 两表 + 3 索引；setup.py 版本号同步；`migrate_v223.py` / `migrate_v230_part2.py` 两个迁移脚本退役删除。**立规则**：`init_tables()` 是唯一建表真相，migrate 脚本升完立即退役。

### v2.3.0-part1.1 — 2026-04-18 (hotfix)

修复 `backup_manager.py` 缺失模块级 `operation_hook` 包装函数导致 `api_server` 启动 ImportError。在文件底部追加 5 行模块级便捷函数。**立规则**：对外 import 契约首次交付即提供模块级包装，凡其他文件会 `from X import y`，y 必须在 X 模块 top-level def/class。

### v2.3.0-part1 — 2026-04-16

仪表盘工具箱整体优化 + 批量重跑与 AI 去重联动 + Step 8 增量重复检测 bug 修正。
- **F049**：合并三种重复检测为"智能重复检测"三选一；仪表盘新增 3 张标签分布卡（Card 12/13/14 覆盖 A/C/D 组）；侧边栏一级标签筛选；新增 `/api/tools/duplicate_unified`
- **F059**：提取管理第 4 卡"批量重跑"；候选列表含注解警告 + 截断计数；`operation_hook("batch_rerun")` 强制备份 + 逐文件只删 pending（保留 confirmed/ignored 审核成果）+ 跨文件 `scan_incremental` 去重联动
- **Step 8 bug**：`extract_from_file` 原用 `info["id"]` 实际应是 `info["kp_id"]`（自 v2.2.0 潜伏），导致增量重复检测从未触发

### v2.2.3 — 2026-04-12 (hotfix)

- **F057 R1 截断自动补救**：保留已解析 kp，末条 excerpt 三级定位（完整匹配 → 首 30 字 → 尾 30 字反向），取尾段重提最多 3 次降级至 500 字
- **F058 质检三级降级链**：L0 批量 15 → L1 小批 3×2 轮 → L2 逐条 → L3 规则兜底；守门员强制兜底；qa_source 字段新增
- **F060 关键操作强制备份**：6 触发点接入 `operation_hook`；保留策略每 op_name 5 个 + 2GB 上限
- **F061 历史质检补跑**：`/api/tools/qc_rerun` 扫未质检/格式异常 kp
- **事件日志**：`operation_events` 表 + `/api/events` 查询 + 仪表盘 Card 11 截断补救

```sql
ALTER TABLE source_files ADD COLUMN truncation_count INTEGER DEFAULT 0;
ALTER TABLE source_files ADD COLUMN recovery_runs INTEGER DEFAULT 0;
ALTER TABLE source_files ADD COLUMN last_recovery_at TEXT;
ALTER TABLE knowledge_points ADD COLUMN qa_source TEXT DEFAULT 'batch';
CREATE TABLE operation_events (...);
CREATE INDEX idx_events_time / idx_events_type / idx_events_file;
```

### v2.2.2 — 2025

重复检测合并与批量处理：F051-F054 多选合并 / 批量解决 / 跨页全选 / 自动刷新按钮计数。F039 重复检测 V3 精判补齐 client 参数，消除假阳性。

### v2.2.1 — 2025

重复组多选保留：勾选框 + keep_ids 数组，支持保留多条有价值的知识点。

### v2.2.0 — 2025

专家注解 + 经验速记：F029 专家注解 5 类型（纠错 / 补充 / 情境 / 反例 / 引用）+ F045 经验速记 V3 结构化入库 + 预处理保存 .md 缓存。

### v2.1.2 — 2025

长任务管理 + 版本重提取：F046 管理后台（Tab 双视图）+ F047 长任务 threading + 2 秒轮询进度 + F044 版本重提取（PROMPT_VERSION 追踪）。

### v2.1.1 — 2025

F028 政策依赖校验 + F039 重复检测（本地粗筛 + V3 精判）。

### v2.1.0 — 2025

三层标签体系 + 保鲜：F021-F027 三层标签（6 组 41 个一级标签 + 8 维度属性 + 关键词）+ F028 保鲜扫描（checked_at + interval_days）。

### v2.0.0 — 2025

Flask 本地 Web 管理后台。Tab 双视图 + 知识点 CRUD + 编辑历史追溯。

### v1.x — 2024

基础提取引擎：R1 提取 + 硅基流动 OCR + SQLite 底座。双 API 架构（DeepSeek 推理 + 硅基流动仅 OCR）。

---

## 附录：完整历史

更详细的每版交付清单（完整 Added/Fixed/Changed/验证清单 / 设计决策 Q&A / dry run 数据 / 老唐操作清单）见 [GitHub Releases](https://github.com/Fat-designer920/rural-revitalization-kb/releases) 和 Git commit 记录。

**重构说明**（2026-04-24）：本 CHANGELOG 自 v2.3.0-part3 起采用"近 3 版完整 + 早期折叠"格式，总体积从 1021 行压缩到约 300 行。立规则与架构契约已迁移至 `01_工程手册.md`，不再在 CHANGELOG 重复。未来新版本仅保留最近 3 版完整记录，老版本顺延折叠。
