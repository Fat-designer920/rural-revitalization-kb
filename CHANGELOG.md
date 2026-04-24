# CHANGELOG

> 乡村振兴知识库搭建助手 — 版本变更记录
>
> 格式：近 3 版完整 Added / Fixed / Changed / Migration 四段式。早期版本折叠为一行摘要，完整历史见 [GitHub Releases](https://github.com/Fat-designer920/rural-revitalization-kb/releases)。

---

## [v2.3.0-part3.6] - 2026-04-24 (hotfix)

**定位**:诊断包首版三 bug 一次清除 + 沉淀三条工程纪律。从"导出看得到文件"升级为"导出拿到手的报告是准的"。

### Fixed

- **Bug 1 — 六维度得分表权重列全 0**:`e2e_tester._run_pipeline` 构造 `full_report` 时漏写 `dim_weights` 字段,权重常量 `DIM_WEIGHTS_DEEP/QUICK` 在 `_compute_total_score` 里用完就扔。exporter 读 `fr.get("dim_weights")` 永远拿空字典。**修复**:tester 写入侧补 `"dim_weights": dict(weights)` + exporter 读取侧加历史报告兜底(按 `scan_depth` fallback 到常量)。老报告不用重跑
- **Bug 2 — 白名单过滤永远显示"无过滤项"**:白名单行号仍停在 db_manager.py v2.3.0-part3.2 基准,对齐不上 part3.4 真实行号,67+11 条零命中。**修复**:exporter 加失效自检 —— `filtered_out` 空 + dim4/dim6 命中 ≥20 条 → 输出"⚠️ 白名单可能已失效"警告(不再静默说"无过滤")。重扫白名单对齐 part3.4 行号是独立体力活,留单独 hotfix
- **Bug 3 — 近 7 天事件日志永远空**:exporter SQL 字段名拼错 `created_at` / `payload`,真实字段是 `event_time` / `payload_json`,运行时 `no such column` 被 except 静默接住。**修复**:查询 SQL + 渲染读取两处字段名全修正
- 所有修复按**立规则第 50 条 6 项拉通验证**跑过:语法 + 字段名 grep + 调用点 + 新旧数据兼容 + 写入/读取契约对齐 + import 双路径

### Added

- **立规则第 49 条**:大文件小改动(≥300 行 且 ≤5 处)用"拷贝 + 局部替换"工作流,不重出整文件。md 项目文件同样适用
- **立规则第 50 条**:局部修改后必跑 **6 项拉通验证**再 `present_files` —— 语法 / 字段名漏网 / 调用点 / 新旧数据 / 跨文件契约 / import 路径。与第 49 条配套,防"单点写对但没回头拉通"
- **立规则第 51 条(元规则)**:项目文件改完也要"拉通 + 做减法"。核心法则 —— 凡老唐每次会发源码给 Claude 的内容,不在 md 里展开细节;立规则/踩坑/决策"为什么"要留,论证过程/长篇举例要删。与 47/48 条三位一体,分别管"写什么"/"不写什么"/"每次更新做减法"。**自证**:part3.6 首版第 49/50 条各 500 字,按第 51 条压到 200 字

### Changed

- `scripts/e2e_tester.py` v2.3.0-part3.4 → **v2.3.0-part3.6**(+11 行)
- `scripts/e2e_diagnosis_exporter.py` v2.3.0-part3.5 → **v2.3.0-part3.6**(+74 行)
- `00 / 01 / CHANGELOG / README` 全量同步,立规则总数 48 → 51
- 立规则第 9 条追加 part3.6 第 4 次应验案例

### Migration

无 schema / 无迁移 / 无新增路由 / 无数据转换。纯代码替换 + 项目文件同步。

### Upgrade Path

1. 替换 `scripts/e2e_tester.py` + `scripts/e2e_diagnosis_exporter.py`
2. 推送 GitHub → 重启 `启动后台.bat`
3. 验证:工具箱→端到端测试→跑一次 deep 扫描→弹窗 footer 点"导出诊断包"→检查新报告三项:① 六维度得分表"权重"列显示 0.12/0.20 等真实数字(不全 0);② 第三段显示"⚠️ 白名单可能已失效"警告(或有真实过滤条目);③ 第五段显示近 7 天的 warn/error 事件(不是"无事件")
4. 老诊断包(part3.5 导出的 9 号报告)不受影响,exporter 读取侧有 fallback

**工程细节详见**:`01 §四 诊断包三 bug 修复 v2.3.0-part3.6 锁定` + `01 立规则 49/50/51 条`

---

## [v2.3.0-part3.5] - 2026-04-24 (feature)

**定位**:F062 配套 —— E2E 诊断包 Markdown 导出。跑完 E2E 一键打包发 Claude 做异地诊断,把 issue 审查从"网页逐条切四态"前置为"整包批量诊断"。

### Added

- **新模块 `scripts/e2e_diagnosis_exporter.py`**(~574 行,纯读格式化):唯一对外入口 `build_e2e_diagnosis_markdown(db, report_id) -> (md_text, filename)`。7 段 Markdown:元数据 / 六维分 / 白名单 / issue 聚合清单(按 `rule_id+file+dim_code` 三元组合并,含命中行号列表 + 典型代码片段) / 近 7 天事件日志摘要 / 使用说明 / 版本上下文
- **`scripts/api_server.py`** 新增路由 `GET /api/tools/e2e/export/<rid>`,Response 带 `Content-Disposition: attachment`,浏览器直接下载
- **`web/templates/review.html`** E2E 报告弹窗 footer 加"导出诊断包"按钮 + `doE2eExportDiagnosis()` JS 函数
- **立规则第 47 条 + 第 48 条**:项目文件精简够用(防文档工程师陷阱)+ 工程手册只记"代码里读不出的信息"(与 47 条互补,利用"每次修改都上传最新代码"这个事实)。详见 `01 §二立规则` + `§十二设计思想第 18 条`。本轮倒回头把工程手册从 1267 行压到 809 行(-36%)

### Fixed / Changed

- 无 bug 修复。版本号:api_server.py / review.html / 新 exporter 模块 均 v2.3.0-part3.5。项目文件全量更新(00/01/CHANGELOG/README)

### Migration

无 schema / 无迁移 / 无新增路由冲突 / 纯读零副作用。

### Upgrade Path

1. 新增 `scripts/e2e_diagnosis_exporter.py`
2. 替换 `scripts/api_server.py` + `web/templates/review.html`
3. 推送 GitHub → 重启 `启动后台.bat`
4. 验证:工具箱→端到端测试→查看最近报告→弹窗 footer 应有三个按钮(查看 issue / 导出诊断包 / 关闭)→点导出得到 `e2e_diagnosis_<rid>_<ts>.md`

**工程细节/设计决策详见**:`01 §四关键设计决策` + `01 §6.5 模块结构速查` + `01 §5.3 API 路由速查-F062`

---

## [v2.3.0-part3.4] - 2026-04-23 (hotfix)

**定位**：质量闭环从"能跑"到"能真正指路" —— 修复两个让仪表盘数字"漂亮但是假"的 bug

### Fixed

**Bug 1 — 体检维度 5 低分打磨永久 100 分 + 自动跳过**

- **现象**：仪表盘明明显示 1 分 2 条、2 分 33 条共 35 条低分条目，全库体检报告却显示"全库无低分条目(1-2 分共 0 条),已跳过打磨环节"，维度 5 得分 100 分。
- **位置**：`scripts/db_manager.py` `get_polish_candidates()` line ~1960
- **根因（业务现状漂移，潜伏自 part3.2 就绪度联动上线约 1 个月）**：
  1. 旧 WHERE 子句 `review_status NOT IN ('ignored','confirmed','merged')` 排除了 `confirmed`（已入库）条目
  2. 这在 v2.3.0-part2（F048 上线时）是合理的——那时审核流程是"打磨完才入库"
  3. part3.2 上线就绪度联动后，`qa>=4 AND draft → quotable` 自动升 confirmed；全库最终都会 confirmed 化
  4. 当前库 2436 条 100% confirmed，旧过滤条件把所有低分条目一并过滤掉，维度 5 永久 100 分
- **修复**：WHERE 排除集合收紧为 `('ignored','merged')`。允许 `confirmed` 条目进候选池。纵向边界 `qa_score>0 AND qa_score<=2` 保持不变（立规则第 40 条核心语义）
- **立规则第 40 条补注**：加"横向边界"说明，明确 confirmed 允许进候选池
- **立规则第 17 条（设计思想）新增**：筛选条件的边界要跟业务现状对齐，业务流程变化时 WHERE 子句必须回头校对

**Bug 2 — 端到端测试 Issue 列表显示 0 条，但报告显示 185 个 issue**

- **现象**：F062 端到端测试报告显示维度 3/4/6 共 185 个 issue（维度 4 字段契约 95 / 维度 6 代码异味 88 / 维度 3 Prompt 2），但点"查看 issue 列表"弹窗显示"Issue 四态列表 共 0 条 / 当前筛选无 issue"。
- **位置**：`scripts/e2e_tester.py` `_write_issues()` line ~1013 + `_run_pipeline()` line ~462
- **根因（签名漂移 + 调用顺序错误，潜伏自 F062 上线 part3 约 1 个月）**：
  1. `db.upsert_e2e_issue` 真实签名是 `upsert_e2e_issue(report_id, dim_code, endpoint, severity, signature, payload=None)`
  2. `_write_issues` 错误调用用了 `rule_id=` / `detail=` 两个**签名里不存在**的关键字参数
  3. 且没传必填的 `report_id`（`_write_issues` 被调用时 `report_id` 还没生成）
  4. 每条 upsert 抛 `TypeError: unexpected keyword argument 'rule_id'` 被 `_safe_log_event` 静默接住
  5. 结果：`e2e_issues` 表实际 0 条落库，但报告摘要已经在内存算出 185 条显示给前端
- **修复**：
  - `_write_issues(issues)` 签名扩为 `_write_issues(issues, report_id)`
  - 内部调用对齐真实签名：`rule_id` / `detail` 合并进 `payload` 字典，数据不丢
  - `_run_pipeline` 调用顺序调整：旧"六维度 → write_issues → save_report"改为"六维度 → save_report(拿 report_id) → write_issues(report_id)"
  - `upserted_count` 从 `full_report_json` 顶层移除（过去没前端消费），改为 `e2e_issue_summary` 事件日志记录
- **立规则第 9 条第三次应验**：F058→F061(part3.1)、`upsert_e2e_issue`(part3.4) 都是"改一侧没改另一侧"的签名漂移；签名必 grep 源码对照，不能靠记忆

### Changed

- `scripts/db_manager.py` 版本号 v2.3.0-part3.2 → **v2.3.0-part3.4**（加 part3.2 历史变更条目 + part3.4 hotfix 条目）
- `scripts/e2e_tester.py` 版本号 v2.3.0-part3.3 → **v2.3.0-part3.4**
- `scripts/api_server.py` 版本号注释 v2.3.0-part3.2 → **v2.3.0-part3.4**（代码无实质改动，仅同步版本号）
- `web/templates/review.html` 版本号 v2.3.0-part3.3 → **v2.3.0-part3.4**（代码无实质改动，仅 title 和页面头版本号文本）
- `00_项目全景.md` / `01_工程手册.md` / `CHANGELOG.md` / `README.md` 同步到 part3.4
- `01_工程手册.md`：
  - 代码清单 4 个文件版本号更新
  - 立规则总数说明：46 条不变，本次无新增立规则
  - 立规则第 9 条追加 part3.4 应验案例
  - 立规则第 40 条追加横向边界补注
  - 关键设计决策 §四新增"低分打磨候选池 / E2E issue 签名漂移（v2.3.0-part3.4 锁定）"9 条决策
  - 架构速查 `get_polish_candidates` 方法签名说明加横向边界注释
  - 退役组件表新增 2 条（confirmed 排除 / `_write_issues` 旧签名）
  - 设计思想新增第 17 条"筛选条件的边界要跟业务现状对齐"

### Migration

- **无 schema 变更** / 无迁移 / 无新增路由 / 无新增立规则
- 老唐操作：替换 4 个文件 → 推送 GitHub → 更新 Claude Projects 项目文件 → 启动后台
- **下次体检警告**：修复后维度 5 会实打实扫到约 35 条低分候选并跑打磨降级链。API 成本估算：
  - 快速档（30/50/100/200）：`polish_max` 会限流，≤0.5 元
  - 完整档（不设 polish_max）：全 35 条跑，约 0.5-1.0 元 / 5-15 分钟
- **下次 E2E 扫描警告**：修复后 deep 档会产生约 134 条 pending issue（185 - 51 白名单），需要逐条切"已修/忽略"

---

## [v2.3.0-part3.3] - 2026-04-23 (hotfix)

**定位**：后台 UI 可信度清扫（3 处 UX 顽疾）+ E2E 白名单漂移实债偿还

### Added

- **立规则第 46 条**：前后端契约同步升级。后端改 API 返回结构时前端所有消费点必须同步改；兜底 `if(!h) showToolResult(pre(JSON))` 是临时救命草不是长期方案
- **设计思想第 15 / 16 条**：前后端是两条腿必须一起迈 / "看起来完成" vs "用户能用"

### Fixed

**Bug 1 — 审核统计 A 卡显示裸露的 JSON 字符串**

- **现象**：点"审核统计"按钮，弹窗直接显示 `<pre>{"overview":{...},"field_edits":{...}}</pre>` 原始 JSON
- **位置**：`web/templates/review.html` `runTool("analytics")` 分支
- **根因（潜伏自 review_analytics v2.1.2 约 2 个月）**：
  1. 后端 `review_analytics.get_analytics_json()` 从扁平结构（`total_reviewed / confirmed / avg_qa_score / top_flags`）升级为 6 段嵌套（overview / field_edits / type_edit_rates / prompt_versions / qa_distribution / qa_flags）
  2. 前端 `runTool("analytics")` 仍按老扁平字段读，全部 undefined
  3. 兜底分支 `if(!h) showToolResult("<pre>"+JSON.stringify(r)+"</pre>")` 触发
- **修复**：前端按 6 段结构化重写，每段独立渲染卡片

**Bug 2 — 保鲜扫描点击后视觉无反馈**

- **现象**：点"保鲜扫描"按钮后卡片只是 `opacity:.5` 变灰，用户不确定在不在跑
- **修复**：加 loading 弹窗（旋转图标 + "保鲜扫描中,预计 1-3 秒..." 文字），扫描完弹 confirm 跳转

**Bug 3 — 体检维度 5 低分打磨得分 100 分时用户困惑**

- **现象**：体检报告维度 5 显示 100 分，但用户不知道是"没跑"还是"跑了但无可打磨"
- **修复**：`renderHealthReport` 增强：`low_score_count=0` 时显示"全库无低分条目(1-2 分共 0 条),已跳过打磨环节"（**注：此修复在 part3.4 暴露出 Bug 1 的根因—— WHERE 子句过滤把 confirmed 条目全排除了，low_score_count=0 是假的**）

**Bug 4 — E2E 报告耗时 `<1 秒` 时显示 `0s`**

- **现象**：quick 档秒级完成，报告显示"耗时 0s"
- **位置**：`review.html` E2E 报告渲染
- **根因**：`int(time.time()-start)` 向下取整，毫秒级场景误显 0s
- **修复**：前端 `<1s` 兜底显示

**Bug 5 — F062 白名单行号漂移导致 issue 暴涨**

- **现象**：维度 4 issue 140 / 维度 6 issue 94 / 总分跌到 69.92
- **位置**：`scripts/e2e_tester.py` `DIM4_KNOWN_FALSE_POSITIVES` / `DIM6_KNOWN_FALSE_POSITIVES`
- **根因**：part3.2 新增 `promote_readiness_by_qa_score` / `get_readiness_promote_preview` 导致 db_manager.py 下游行号全部漂移，原 41 条白名单全部失效
- **修复**：
  - DIM4: 35 条 → 67 条
  - DIM6: 6 条 → 11 条（每个 pass 点位覆盖 except 行 + body 行，兼容 handler.lineno / body[0].lineno 两种实现）
  - WHITELIST_REASONS: 同步更新为 78 条
- **立规则 §5.8 强化**：db_manager.py 重构后 F062 白名单行号必须重扫刷新

### Changed

- `web/templates/review.html` v2.3.0-part3.2 → v2.3.0-part3.3（审核统计 6 段重写 + 保鲜 loading + 体检 note + E2E 耗时兜底）
- `scripts/e2e_tester.py` v2.3.0-part3.2 → v2.3.0-part3.3（白名单行号刷新）

### Migration

- 无 schema 变更 / 无迁移
- 老唐操作：替换 2 个代码文件 → 启动后台验证 4 个 UI

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

---

## 早期版本精简摘要

### v2.3.0-part3.2 — 2026-04-23 (hotfix)

仪表盘可信度修复 + 质检补跑异步化 + 就绪度联动预埋,一次三件事交付。**Bugs**:(A)三张标签分布卡"暂无数据"—— `get_tag_distribution` 用 `tag_code` 查 `tag_name` 存储,潜伏 3 个月,旧版靠"count=0 也塞入"掩盖;(B)前端 `renderTagCard.getName` 未兼容 `tag_name` 字段;(C)折叠按钮用 DOM.childElementCount 反推总数错位;(D)仪表盘"未质检 0"vs"待补跑 2043"口径打架;(E)质检补跑同步阻塞刷新即失;(F)卡片标题泄露内部版本号。**Added**:独立 `_qc_task` 任务槽支持与主槽并发 + 独立 `#qcTaskProgress` 进度面板 + 刷新自动恢复 + 工具箱"就绪度联动"按钮(R 橙,保守前置版本:qa≥4 且 draft→quotable 只升不降,不碰 premium)。**立规则第 10 条**:存储/查询口径一致性(针对 JSON 字段的 SQL 查询前必须对照存储侧写入逻辑确认格式)。

### v2.3.0-part2.2 — 2026-04-22 (hotfix)

F048 四类系统性 bug 修复 + 启动就绪性自检。`_health_readiness_check()` 4 层自检模板（Prompt / DB / client / schema 字段契约）放 `_task_lock` 之前；db_manager 三扫描查询 LEFT JOIN categories；prompt_templates 补齐 6 个 F048 Prompt 正式版；health_checker.py 所有 `HEALTH_*_PROMPT` 改顶层 import、删除 try/except fallback 和 6 处 `if not PROMPT: return None`；6 处 `['system']` → `['system_prompt']`、6 处 `['user']` → `['user_prompt_template']`。立规则 1-5 条。

### v2.3.0-part2 — 2026-04-22

F048 知识库体检 Agent 三对话拆分全闭环（基础层 + 引擎层 + 界面层）：prompt_templates（6 个 F048 Prompt）+ db_manager（+2 表 +12 方法）+ `health_checker.py`（新建 ~1360 行，六维度 + 三层打磨降级链 + 孤岛精判 + 变现报告）+ api_server（+8 F048 路由）+ review.html（+603 行，工具箱第 10 卡 + 3 模态框 + 13 JS 函数）。v2.3.0-part2.1 hotfix 将两表吸收进 init_tables，migrate 脚本退役。

### v2.3.0-part3-alpha2 — 2026-04-23 (alpha)

F062 对话 2/3 引擎层 `e2e_tester.py`（~1250 行）新建。六维度扫描 + V3 调用五方法两签名适配器 + 白名单二次过滤（dim4 35 + dim6 6 = 41 unique signature）+ 9 stage progress_callback + 16 种 operation_events 埋点。

### v2.3.0-part3-alpha1 — 2026-04-23 (alpha)

F062 对话 1/3 基础层：prompt_templates（+E2E_RESPONSE_JUDGE_PROMPT）+ db_manager（+3 表 +8 方法）+ `static_analyzer.py`（新建 645 行，维度③④⑥ AST 规则库）。SQLite 表总数 18 → 21。

### v2.3.0-part1.1 — 2026-04-18 (hotfix)

修复 `backup_manager.py` 缺失模块级 `operation_hook` 包装函数导致 `api_server` 启动 ImportError。**立规则**：对外 import 契约首次交付即提供模块级包装。

### v2.3.0-part1 — 2026-04-16

仪表盘工具箱整体优化 + 批量重跑与 AI 去重联动 + Step 8 增量重复检测 bug 修正。F049 智能重复检测三选一 + **仪表盘 3 张标签分布卡**（part3.2 修复其存储/查询口径 bug） + 侧边栏一级标签筛选；F059 批量重跑（operation_hook 强制备份 + 逐文件只删 pending + 跨文件 scan_incremental 去重联动）；Step 8 修正 `info["id"]` → `info["kp_id"]`（自 v2.2.0 潜伏）。

### v2.2.3 — 2026-04-12 (hotfix)

F057 R1 截断自动补救（三级定位，最多 3 次降级至 500 字）+ F058 质检三级降级链（L0 批量 → L1 小批 → L2 逐条 → L3 规则兜底 + 守门员兜底）+ F060 关键操作强制备份（6 触发点）+ F061 历史质检补跑（`/api/tools/qc_rerun`）+ `operation_events` 表。**注**：F058 重构 `_quality_check` 扩成 5 参，F061 调用未跟上 → v2.3.0-part3.1 修复；F061 同步执行架构不可并发、不可观测 → v2.3.0-part3.2 异步化。

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

三层标签体系 + 保鲜：F021-F027 三层标签 + F028 保鲜扫描（checked_at + interval_days）。**注**：三层标签体系本版上线时 `extractor._sanitize_tags` 存 tag_name，但 v2.3.0-part1 的 `get_tag_distribution` 用 tag_code 查询，潜伏 3 个月至 v2.3.0-part3.2 修复。

### v2.0.0 — 2025

Flask 本地 Web 管理后台。Tab 双视图 + 知识点 CRUD + 编辑历史追溯。

### v1.x — 2024

基础提取引擎：R1 提取 + 硅基流动 OCR + SQLite 底座。

---

## 附录：完整历史

更详细的每版交付清单见 [GitHub Releases](https://github.com/Fat-designer920/rural-revitalization-kb/releases) 和 Git commit 记录。

**重构说明**（2026-04-24）：本 CHANGELOG 自 v2.3.0-part3 起采用"近 3 版完整 + 早期折叠"格式，立规则与架构契约已迁移至 `01_工程手册.md`，不再在 CHANGELOG 重复。未来新版本仅保留最近 3 版完整记录，老版本顺延折叠。
