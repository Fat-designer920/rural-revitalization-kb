# CHANGELOG

> 乡村振兴知识库搭建助手 — 版本变更记录
> 格式：[版本号] - 日期 - 标题 / 修复 / 新增 / 变更 / 数据库变更 / 回滚方案

---
## v2.3.0-part1 (2026-04-20)
 
**定位**：工具箱整体优化 + 批量重跑与 AI 去重联动 + Step 8 顺手修。
 
### F049 仪表盘工具箱优化 ✨
- **合并三种重复检测为单一入口**：工具箱的"全库重复检测"和"清理并重扫"两张卡合并为一张"智能重复检测"，点击弹出三选一对话框：
  - 最近 7 天（约 2-3 毛）
  - 全库扫描（约 3-5 毛）
  - 彻底重扫（约 5-8 毛，强制备份 + 清 pending + V3 全库重扫）
- **仪表盘新增 3 张标签分布卡**：
  - Card 12 业务领域分布（A 组 13 个标签）
  - Card 13 知识形态分布（C 组 9 个标签）
  - Card 14 客户视角分布（D 组 5 个标签）
  - 每张卡默认显示 Top5 dBar + 底部"展开全部 N 个"按钮
  - 所有标签支持点击穿透跳转到审核列表（新增 `layer1_tag` 筛选参数）
- **新增后端接口**：`POST /api/tools/duplicate_unified`，请求体 `{mode:"recent"/"full"/"reset_rescan", days?:7}`
- **侧边栏新增一级标签筛选条件区**：`#layer1TagFilterSection`，默认隐藏，仅当通过穿透跳转设置 `currentLayer1Tag` 后显示当前标签 + 清除按钮
- **新增 db_manager 方法**：`get_tag_distribution(group)` 按组统计 A/C/D 三层标签的使用频次
### F059 批量重跑 + AI 去重联动 ✨
- **提取管理新增第 4 张卡"批量重跑"**（图标 "4"）
- **候选列表 UI**：文件名 + 知识点计数 + 含注解警告（橙色）+ 截断计数
- **执行流程**：
  - Step 1：`operation_hook("batch_rerun")` 强制备份，失败直接终止
  - Step 2：逐文件 `delete_extracted_kps_by_source_file`（只删 pending，保留 confirmed/ignored 审核成果）
  - Step 3：逐文件走 `extract_from_file` 完整提取链（F057 截断补救 / F058 质检降级 / Step 8 去重联动）
  - Step 4：全部完成后统一跑 `scan_incremental` 跨文件 AI 去重
- **新增后端接口**：
  - `GET /api/tools/batch-rerun-scan` 扫描候选文件列表
  - `POST /api/tasks/batch_rerun` 启动批量重跑任务（task type="batch_rerun"）
- **含注解文件不禁用**：注解的保留依赖 db 层 `delete_extracted_kps_by_source_file` 合约（只删 pending knowledge_points，不触 annotations 表）
- **进度条复用既有任务框架**：`checkRunningTask` 的 titles 字典新增 "batch_rerun":"批量重跑进行中"
### 🐛 Bug 修复
- **Step 8 增量重复检测从未触发**：`extract_from_file` Step 8 原代码用 `info["id"]`，但 `kps_info` 实际存的是 `"kp_id"`，导致 `new_ids` 一直为空。v2.3.0-part1 改为 `info["kp_id"]`，每次提取后增量重复检测恢复正常触发。该 bug 自 v2.2.0 起潜伏至今。
### 📦 向下兼容
- `/api/tools/duplicate-scan` 和 `/api/tools/duplicate-reset-rescan` 两个旧接口保留不变，供浏览器缓存的旧 review.html 继续调用
### 🎨 前端改动汇总（review.html）
- Header 版本号 v2.2.3 → v2.3.0-part1
- 工具箱卡片数 10 → 9（合并两张为一张）
- 提取管理卡片数 3 → 4（新增批量重跑）
- 仪表盘卡片数 11 → 14（新增 A/C/D 标签分布三张）
- 新增 `currentLayer1Tag` 全局状态串联 dashJump / loadKnowledgePoints / showActiveFilters / clearAllFilters
- 新增函数：`updateLayer1TagFilterSection` / `clearLayer1TagFilter` / `renderTagCard` / `toggleTagCardMore` / `doDupUnified` / `_runDupUnified` / `showBatchRerunPanel` / `brToggleAll` / `doBatchRerun`
- 新增模态框：`#dupModeDlg`（三选一对话框）、`#batchRerunPanel`（批量重跑面板）
### v2.2.3 既有元素原样保留
- Card 11 截断补救 / 事件日志按钮 / 规则兜底黄色高亮 / qa_source 筛选器 / qaBackfill 降级链 — 一字不改
---
 
## v2.2.3 (2026-04 hotfix)
 
- F057 截断自动补救（excerpt 定位切分点 + 尾段重提，3 次降级至 500 字）
- F058 质检三级降级链（批量 15 → 小批 3×2 → 逐条 → 规则兜底）+ QC_CHECK_SINGLE_PROMPT
- F060 关键操作强制备份（`operation_hook` 钩子 + `BackupFailedError` + 每类保留 5 个 / 总量 2GB）
- F061 历史质检补跑（`/api/tools/qc_rerun` + 降级链）
- 新建 `operation_events` 结构化事件日志表
- v2.1.2 分批质检内层循环 bug 顺手修
- `_extract_single` 返回值契约统一为 dict

## [v2.2.3] - 2026-04-18 — 紧急 Hotfix（三对话分批交付，全部完成）

### 修复（Fixes）
- **F057 R1 输出截断自动补救**：R1 输出 JSON 截断时不再丢失已提取内容；保留 deepseek_client 已解析的完整知识点，用最后一条 excerpt 定位切分点（三级定位：完整匹配→首30字→尾30字反向），重新提取尾段（最多 3 次降级至 500 字）；按 `(title, excerpt前100字)` 去重合并
- **F058 质检三级降级链**：修复 V3 批量质检格式异常时条目直接跳过（qa_score 空置）的问题。新链路：`L0批量15→L1小批3×2轮→L2逐条（QC_CHECK_SINGLE_PROMPT）→L3本地规则兜底`；新增守门员机制确保每条 kp 都有 qa_score
- **v2.1.2 分批质检内层循环 bug**：原代码 `for qr in results` 实际只遍历最后一批 results，多批质检时前面批次分数未写入 DB；v2.2.3 重写 `_quality_check` 走三级降级链时天然消除
- **api_server 死代码清理**：删除 `task_reextract` 函数末尾 `return` 之后永远走不到的 `import time; time.sleep(1.5); webbrowser.open(...)`

### 新增（Features）
- **F060 关键操作强制备份**：5 个触发点（版本重提取/批量重跑/重复合并单条与批量/体检采纳/全库重扫）接入 `backup_manager.operation_hook(op_name)`。v2.2.3 已接入 4 处（reextract / dup_merge / dup_merge_batch / full_rescan），另 2 处（batch_rerun F059 / health_adopt F048）留给 v2.3.0 时在对应功能内接入
- **F060 备份保留策略**：每类 `op_name` 保留最近 5 个 + 总量 2GB 上限（每类兜底保留 1 个）；备份文件名保留秒级 `backup_YYYYMMDD_HHMMSS_op_name.db`；备份失败抛 `BackupFailedError`，调用方精确捕获后终止操作
- **F061 历史质检补跑**：`POST /api/tools/qc_rerun` 扫 `qa_score IS NULL` 或 `qa_flags 含"格式异常"` 的条目，走 F058 降级链重跑；`GET /api/tools/qc_rerun/summary` 返回候选数量供前端按钮角标显示；按文件分组逐组补跑，自动加载 .md 缓存作为 source_content 供规则兜底反幻觉
- **事件日志查询**：`GET /api/events?event_type=&severity=&module=&file_id=&limit=500` 查询 `operation_events` 结构化事件日志
- **截断摘要接口**：`GET /api/tools/truncation_summary` 返回受影响文件数 / 累计截断次数 / 累计补救次数
- **qa_source 字段与筛选器**：`knowledge_points` 表新增 `qa_source` 字段（值域 `batch/small_batch/single/rule_fallback`）；审核界面侧边栏加"质检来源"筛选区（4 选项）；规则兜底条目整卡黄色高亮（`#FFFBEF` + 左侧橙色边框）+ "规则兜底" 小标签
- **仪表盘"截断补救"卡（Card 11）**：显示受影响文件数 + 累计截断次数 + 累计补救次数 + 待质检补跑数量；底部双按钮"截断事件"（预设筛选）和"全部事件"打开事件日志模态框
- **事件日志模态框**：880px 宽，6 列表格（时间/类型/严重度/模块/文件ID/详情），支持 event_type + severity 二次筛选
- **工具箱"质检补跑"按钮升级**：点击先查 summary 显示候选数量（未质检 + 格式异常分开计数），确认后走降级链；结果页显示已处理/候选总数/孤儿条目（经验速记）/错误列表/剩余待补跑
- **QC_CHECK_SINGLE_PROMPT（逐条质检）**：6 维度评分，输入单个知识点避免 V3 批量格式异常

### 变更（Changes）
- `extractor.py` `_extract_single` 返回值契约：由"列表 / 'TRUNCATED'字符串"改为统一 dict `{kps, truncated, last_excerpt, raw_parsed, cost}`，调用方须 `result['kps']` 取数
- `extractor.py` `_extract_with_auto_split` 签名新增 `file_id` 参数（补救触发 `db.increment_truncation_count(file_id)` 和事件日志需要）
- `extractor.py` `_quality_check` 签名新增 `source_content` 参数（规则兜底用 `_excerpt_in_source` 做幻觉检查）
- `extractor.py` 新增类级常量 `QC_FLAG_MAP`（原内部局部变量提升，三级降级共用，F048 低分打磨也将复用）
- 旧 `/api/tools/qa-backfill` 接口保留但内部转发到 `_qc_rerun_core()`（向下兼容），字段映射保持原响应格式（`processed→checked`，`errors数组长度→errors数字`）
- 仪表盘 API 响应新增字段：`truncation` / `qc_rerun` / `qa_source_distribution`
- 主页标题和 header 版本号：v2.2.2 → v2.2.3

### 数据库变更（DB Schema）
**必须先执行 `python scripts/migrate_v223.py` 再启动服务**（幂等迁移，纯 schema 变更，无数据迁移）：

```sql
-- source_files 表新增截断追踪字段
ALTER TABLE source_files ADD COLUMN truncation_count INTEGER DEFAULT 0;
ALTER TABLE source_files ADD COLUMN recovery_runs INTEGER DEFAULT 0;
ALTER TABLE source_files ADD COLUMN last_recovery_at TEXT;

-- knowledge_points 表新增质检来源字段
ALTER TABLE knowledge_points ADD COLUMN qa_source TEXT DEFAULT 'batch';

-- 新建结构化事件日志表
CREATE TABLE IF NOT EXISTS operation_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    event_type TEXT NOT NULL,
    module TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info'
        CHECK(severity IN ('info','warning','error')),
    related_file_id INTEGER,
    related_kp_id INTEGER,
    payload_json TEXT DEFAULT '{}',
    FOREIGN KEY (related_file_id) REFERENCES source_files(id),
    FOREIGN KEY (related_kp_id) REFERENCES knowledge_points(id)
);
CREATE INDEX IF NOT EXISTS idx_events_time ON operation_events(event_time);
CREATE INDEX IF NOT EXISTS idx_events_type ON operation_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_file ON operation_events(related_file_id);
```

### 文件变更清单

| 对话批次 | 文件 | 改动类型 |
|---------|------|---------|
| 1/3 地基层 | `scripts/db_manager.py` | 新增 `qa_source` 字段 / `operation_events` 表 / `log_operation_event` / `get_qc_rerun_candidates` / `get_qc_rerun_summary` / `get_operation_events` / `increment_truncation_count` / `get_truncation_summary` |
| 1/3 地基层 | `scripts/backup_manager.py` | 新增 `operation_hook(op_name)` / `BackupFailedError` / 保留策略（每类5个+总量2GB） |
| 1/3 地基层 | `scripts/prompts/prompt_templates.py` | 新增 `QC_CHECK_SINGLE_PROMPT` |
| 1/3 地基层 | `scripts/migrate_v223.py` | 新文件，幂等 schema 迁移 |
| 2/3 引擎层 | `scripts/extractor.py` | F057 截断补救 + F058 质检三级降级链 + 顺手修 v2.1.2 分批质检残留 bug |
| 3/3 界面层 | `scripts/api_server.py` | F060 备份触发点接入 4 处 / F061 补跑 API / 事件日志 API / 截断摘要 API / dashboard 新字段 / 旧 qa-backfill 转发 / 删除死代码 |
| 3/3 界面层 | `web/templates/review.html` | 规则兜底黄色高亮 / qa_source 筛选器 / 质检补跑按钮改造 / 截断补救卡 / 事件日志模态框 |
| 3/3 界面层 | `00_项目全景.md` / `01_工程手册.md` / `03_Prompt手册.md` / `README.md` / `CHANGELOG.md` | 项目文档全量更新 |

### 部署顺序（必读）

1. **先备份**：`启动后台.bat` 里点"一键备份"，或手动复制 `data/knowledge_base.db` 到安全位置
2. **运行迁移**：`python scripts/migrate_v223.py`（幂等，多跑一次也没事）
3. **替换代码**：按 GitHub 提交或本地文件替换 8 个文件
4. **重启服务**：关闭 `启动后台.bat` 后重开
5. **验证**：
   - 仪表盘是否看到 Card 11"截断补救"
   - 工具箱"质检补跑"点一下是否弹窗显示候选数量
   - 审核页侧边栏是否看到"质检来源"筛选区

### 回滚方案
如 v2.2.3 运行出问题：
1. 关闭 `启动后台.bat`
2. 从第 1 步备份还原 `data/knowledge_base.db`
3. 用 Git 回退 `scripts/` 和 `web/templates/` 到上个 tag（v2.2.2）
4. 新开对话反馈错误

### 决策记录（界面层 3 个）
- **旧 `/api/tools/qa-backfill` 保留并转发**：hotfix 最小变更面原则；浏览器缓存的旧版 JS 不会 404；新降级链是旧批量质检的严格超集
- **工具箱"质检补跑"卡改名不新增**：老唐视角只关心功能不关心实现路径；新增第二个按钮会造成"点哪个"的决策成本
- **事件日志入口放仪表盘按钮不单独占工具箱卡位**：日志是场景溯源工具不是巡检工具，独立入口会变成死入口

---

## [v2.2.2] - 2025 — 重复检测合并批量处理

F051-F054 质量管控增强：多选合并 / 批量解决 / 跨页全选 / 自动刷新按钮计数。

## [v2.2.1] - 2025 — 重复组多选保留

重复组勾选框 + keep_ids 数组。

## [v2.2.0] - 2025 — 专家注解 + 经验速记

F029 注解 5 类型 + F045 经验速记 V3 结构化。

## [v2.1.2] - 2025 — 长任务管理 + 版本重提取

F046 管理后台 + F047 长任务 threading + F044 版本重提取。

## [v2.1.1] - 2025 — 政策依赖校验 + 重复检测

F028 政策校验 + F039 重复检测。

## [v2.1.0] - 2025 — 保鲜 + 标签体系

F021-F027 三层标签 + F028 保鲜扫描。

## [v2.0.0] - 2025 — 管理后台

Tab 双视图 + CRUD + 编辑历史。

## [v1.x] - 2024 — 基础提取引擎

R1 提取 + OCR + SQLite。
