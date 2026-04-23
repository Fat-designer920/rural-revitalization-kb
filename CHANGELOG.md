# CHANGELOG

> 乡村振兴知识库搭建助手 — 版本变更记录
>
> 格式：近 3 版完整 Added / Fixed / Changed / Migration 四段式。早期版本折叠为一行摘要，完整历史见 [GitHub Releases](https://github.com/Fat-designer920/rural-revitalization-kb/releases)。

---

## [v2.3.0-part3.1] - 2026-04-24 (hotfix)

**定位**：F061 质检补跑签名漂移 + F062 老库自动追齐 init_tables —— 两个系统性风险一次根治

### Added

- **`scripts/api_server.py`**（+16 行）：模块顶层 `DatabaseManager()` 实例化后追加 `db.init_tables()` 兜底（`CREATE TABLE IF NOT EXISTS` 无副作用，失败打 WARN 不阻塞启动）

### Fixed

**Bug A — F061 质检补跑全线崩溃**
- **现象**：工具箱"质检补跑"点击后 45 个分组全部跳过，0 条成功，候选 2043 条全部卡住，前端"质检补跑结果"弹窗显示"跳过 45 个分组: 文件#2: Extractor._quality_check() missing 2 required positional arguments: 'kps' and 'kps_info'"
- **位置**：`api_server.py` line 1410 + 1421（共 2 处）
- **根因**：F058（v2.2.3）重构 `_quality_check` 把签名从 3 参强制扩成 5 参：`_quality_check(self, filename, content_summary, kps, kps_info, source_content="")`；F061 的 `_qc_rerun_core` 保留旧 2 参调用 `ext._quality_check(kps_list, kps_info, source_content=content)`，Python 把 `kps_list` 当成 `filename`、`kps_info` 当成 `content_summary`，然后 `kps` 和 `kps_info` 真的缺了 → TypeError
- **为什么潜伏 2 个月**：v2.2.3 发布以来老唐从未触发质检补跑，首次触发立刻全线崩
- **修复**：两处调用补齐 `filename`（正常分支用 `renamed_filename`/`original_filename`/`"file_<fid>"` 三级兜底，孤儿分支固定 `"experience_notes"`）和 `content_summary=""`（历史补跑场景无预分析上下文）

**Bug B — F062 三表老库未建，`/api/tools/e2e/latest` 返 500**
- **现象**：后台日志 `sqlite3.OperationalError: no such table: e2e_test_reports`
- **位置**：`api_server.py` line 106 模块顶层 `db = DatabaseManager()` 后从未调用 `init_tables()`
- **根因**：v2.3.0-part3 升级时老唐只替换代码未重跑 `首次安装.bat`，F062 三张新表（`api_endpoint_registry` / `e2e_test_reports` / `e2e_issues`）在 init_tables 里定义好却没机会执行
- **修复**：实例化后 silent 重入 `db.init_tables()`，`CREATE TABLE IF NOT EXISTS` 幂等无副作用

### Changed

- **版本号**：api_server.py 顶部 docstring + main banner 同步升 `v2.3.0-part3.1`
- **立规则新增 2 条**（写入 01 工程手册 §二数据层）：
  - **第 8 条 — api_server 启动兜底 init_tables**：`DatabaseManager()` 实例化后必须 silent 调用一次 `db.init_tables()`。避免"只替换代码不重跑首次安装"导致的老库 schema 漂移
  - **第 9 条 — 跨版本调用外部模块方法前必须对照真实签名**：改动前 `grep -n "def <方法名>"` 查真实签名、对照参数个数和关键字/位置参数区分。这是跨版本开发的强制纪律
- **立规则编号全局顺延**：原数据层 1-7 条后插入新 8、9 条，后续代码层（原 8-19→新 10-21）/ 交互层（原 20-27→新 22-29）/ 流程层（原 28-42→新 30-44）全部 +2
- **项目文件全量更新**：00 / 01 / CHANGELOG / README（02 / 03 无改动）

### Migration

**无 schema 变更**。本次修复纯代码层，老库无需 migration 脚本。升级后首次启动 `启动后台.bat` 时 `db.init_tables()` 自动追齐 F062 三张表（如已存在则幂等跳过）。

### Upgrade Path

1. 备份数据库（可选，本次无 schema 变更，风险极低）
2. 替换 1 个文件：`scripts/api_server.py`
3. 推送 GitHub（Summary: `v2.3.0-part3.1: hotfix F061 质检补跑签名漂移 + F062 老库自动追齐`）
4. 重启 `启动后台.bat`（启动时日志应看到 `v2.3.0-part3.1 hotfix` + `数据库正常` 两行）
5. 验证 Bug A：Tab 2 → 工具箱 → 质检补跑 → 应正常处理候选（不再跳过 45 个分组）
6. 验证 Bug B：Tab 2 → 工具箱 → 端到端测试（青蓝 E 卡） → 点击后不再 500、应正常弹档位选择框

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

## 早期版本精简摘要

### v2.3.0-part2 — 2026-04-22

F048 知识库体检 Agent 三对话拆分全闭环（基础层 + 引擎层 + 界面层）：prompt_templates（6 个 F048 Prompt）+ db_manager（+2 表 +12 方法）+ `health_checker.py`（新建 ~1360 行，六维度 + 三层打磨降级链 + 孤岛精判 + 变现报告）+ api_server（+8 F048 路由）+ review.html（+603 行，工具箱第 10 卡 + 3 模态框 + 13 JS 函数）。v2.3.0-part2.1 hotfix 将两表吸收进 init_tables，migrate 脚本退役。

### v2.3.0-part3-alpha2 — 2026-04-23 (alpha)

F062 对话 2/3 引擎层 `e2e_tester.py`（~1250 行）新建。六维度扫描 + V3 调用五方法两签名适配器 + 白名单二次过滤（dim4 35 + dim6 6 = 41 unique signature）+ 9 stage progress_callback + 16 种 operation_events 埋点。

### v2.3.0-part3-alpha1 — 2026-04-23 (alpha)

F062 对话 1/3 基础层：prompt_templates（+E2E_RESPONSE_JUDGE_PROMPT）+ db_manager（+3 表 +8 方法）+ `static_analyzer.py`（新建 645 行，维度③④⑥ AST 规则库）。SQLite 表总数 18 → 21。

### v2.3.0-part1.1 — 2026-04-18 (hotfix)

修复 `backup_manager.py` 缺失模块级 `operation_hook` 包装函数导致 `api_server` 启动 ImportError。**立规则**：对外 import 契约首次交付即提供模块级包装。

### v2.3.0-part1 — 2026-04-16

仪表盘工具箱整体优化 + 批量重跑与 AI 去重联动 + Step 8 增量重复检测 bug 修正。F049 智能重复检测三选一 + 仪表盘 3 张标签分布卡 + 侧边栏一级标签筛选；F059 批量重跑（operation_hook 强制备份 + 逐文件只删 pending + 跨文件 scan_incremental 去重联动）；Step 8 修正 `info["id"]` → `info["kp_id"]`（自 v2.2.0 潜伏）。

### v2.2.3 — 2026-04-12 (hotfix)

F057 R1 截断自动补救（三级定位，最多 3 次降级至 500 字）+ F058 质检三级降级链（L0 批量 → L1 小批 → L2 逐条 → L3 规则兜底 + 守门员兜底）+ F060 关键操作强制备份（6 触发点）+ F061 历史质检补跑（`/api/tools/qc_rerun`）+ `operation_events` 表。**注**：F058 重构 `_quality_check` 扩成 5 参，F061 调用未跟上，v2.3.0-part3.1 修复。

### v2.2.2 — 2025

重复检测合并与批量处理：F051-F054 多选合并 + 跨页全选 + 自动刷新按钮计数。F039 重复检测 V3 精判补齐 client，消除假阳性。

### v2.2.1 — 2025

重复组多选保留：勾选框 + keep_ids 数组，支持保留多条有价值的知识点。

### v2.2.0 — 2025

专家注解 + 经验速记：F029 专家注解 5 类型 + F045 经验速记 V3 结构化 + 预处理保存 .md 缓存。

### v2.1.2 — 2025

长任务管理 + 版本重提取：F046 管理后台（Tab 双视图）+ F047 长任务 threading + 2 秒轮询进度 + F044 版本重提取（PROMPT_VERSION 追踪）。

### v2.1.1 — 2025

F028 政策依赖校验 + F039 重复检测（本地粗筛 + V3 精判）。

### v2.1.0 — 2025

三层标签体系 + 保鲜：F021-F027 三层标签 + F028 保鲜扫描（checked_at + interval_days）。

### v2.0.0 — 2025

Flask 本地 Web 管理后台。Tab 双视图 + 知识点 CRUD + 编辑历史追溯。

### v1.x — 2024

基础提取引擎：R1 提取 + 硅基流动 OCR + SQLite 底座。

---

## 附录：完整历史

更详细的每版交付清单见 [GitHub Releases](https://github.com/Fat-designer920/rural-revitalization-kb/releases) 和 Git commit 记录。

**重构说明**（2026-04-24）：本 CHANGELOG 自 v2.3.0-part3 起采用"近 3 版完整 + 早期折叠"格式，立规则与架构契约已迁移至 `01_工程手册.md`，不再在 CHANGELOG 重复。未来新版本仅保留最近 3 版完整记录，老版本顺延折叠。
