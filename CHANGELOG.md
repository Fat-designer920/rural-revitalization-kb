# CHANGELOG

> 乡村振兴知识库搭建助手 — 版本变更记录
> 格式:版本号 — 日期 — 定位 / 新增 / 修复 / 变更 / 数据库变更

---

## [v2.3.0-part3-alpha1] - 2026-04-23 (alpha)

**定位**：F062 端到端健康测试 Agent 三对话拆分 — **对话 1/3 基础层（契约 → 骨架关卡）**。

本次交付为 F062 三对话拆分的第一阶段，严格遵守"基础层只动 prompt + db + static_analyzer，不动 api_server/review.html/e2e_tester 任何一行"的纪律。

### 背景

v2.3.0-part2.2 F048 防护层复盘暴露了四类系统性 bug 的根因模式（Prompt 未落地 / import 静默降级 / 字段读取 / Prompt key 错配）。这些 bug 模式都是"运行时才会暴露"的问题，F062 的核心定位就是把这类 bug 从"事后挖"升级为"可主动扫"——用 AST 静态规则库在新代码提交时秒级抓出同类模式，不再等"假绿色生产事故"之后才复盘。

### 设计决策（对话 1 Phase 2 已锁定）

| 决策 | 选择 | 理由 |
|------|------|------|
| A：扫描范围 | **A3 全量六维度** | ③④⑥ 纯 AST 静态规则零 AI 成本；① Flask app.url_map 自省也是零成本；真正花 AI 的只有 ② readiness_check 聚合 + ⑤ 最近事件语义判断 |
| B：触发方式 | **B1 手动触发 + 软提醒** | 对齐 F048 体检节奏；软提醒让老唐记得"长期未扫要看看系统有没有退化" |
| C：issue 跟踪 | **C3 四态** + 偶发升级 | 避免"同一问题反复出现被当新 issue"的报告疲劳；偶发升级机制让真正的"反复偶发"浮到待修 |
| D：深度档位 | **D2 两档** | quick 秒回日常扫 / deep 分钟级深度审计 |

### 3 对话拆分

| 对话 | 层级 | 核心产出 | 状态 |
|------|------|---------|------|
| **对话 1** | **基础层** | **prompt_templates (+E2E_RESPONSE_JUDGE_PROMPT + PROMPT_VERSION 升版) + db_manager (+3 表 +3 索引 +8 方法) + static_analyzer.py (新建 645 行) + 03 Prompt 手册** | ✅ **本次交付** |
| 对话 2 | 引擎层 | e2e_tester.py（新建，~1000 行，六维度扫描 + V3 调用封装 + issue 去重写入 + 已知合理项白名单过滤） | 待开发 |
| 对话 3 | 界面层 | api_server（+F062 6-8 路由）+ review.html（工具箱第 11 卡 + 报告弹窗 + issue 四态切换 UI）+ 收尾（check_system/db_health_check/setup 扩清单 + README + CHANGELOG） | 待开发 |

### Added

**scripts/prompts/prompt_templates.py（v2.3.0-part2.2 → v2.3.0-part3-alpha1）**

- 新增 `E2E_RESPONSE_JUDGE_PROMPT` 正式版文本（V3 内省型 Prompt）：
  - 定位：对单次 HTTP 调用的响应 + 最近相关 operation_events，判断是"真成功"还是"假绿色"
  - 双 key 严格：`system_prompt` / `user_prompt_template`（严格对齐对话 A 立规则）
  - 6 个占位符：`{endpoint}` / `{method}` / `{status_code}` / `{response_excerpt}` / `{recent_events_json}` / `{expected_behavior}`
  - 输出：`{judgment: pass|warn|fail, reasons, keywords_hit, confidence}`
  - 3 档判断：pass（真成功） / warn（可工作但瑕疵） / fail（真失败或假绿色）
  - 4 类关键词识别：抢救（rescue/recovery）/ 降级（fallback/downgrade）/ 跳过（skip/bypass）/ 异常继续（exception_swallowed/silent_degrade）
  - 6 条硬约束（写入 system_prompt）：keywords_hit 必须有实际依据 / reasons 不空泛 / 不解读业务语义 / confidence=low 必须说明 / 字面 HTTP 200 + 背后降级 = warn 起步 / 不对产品逻辑做道德评价
- `PROMPT_VERSION` 从 `"v2.3.0-part2.2"` 升到 `"v2.3.0-part3-alpha1"`
- `get_all_prompt_names()` 末尾追加 `{"id": "e2e_response_judge", "name": "E2E-响应语义判断(V3)", "version": PROMPT_VERSION}`
- 文件头 docstring 追加 v2.3.0-part3-alpha1 变更说明段

**scripts/db_manager.py（v2.3.0-part2.2 → v2.3.0-part3-alpha1）**

- 文件头 docstring 追加 v2.3.0-part3-alpha1 变更说明段 + 表清单从 18 张升到 21 张
- `init_tables()` 在 polish_suggestions 建表之后、索引循环之前，追加 3 张 F062 表的 `CREATE TABLE IF NOT EXISTS`：
  - **api_endpoint_registry**：路由登记表（endpoint TEXT PRIMARY KEY + methods + first_seen_at + last_tested_at + test_template_json）
  - **e2e_test_reports**：E2E 测试整体报告（trigger_type + scan_depth + 六维汇总 + new_endpoints_json + full_report_json + v3_call_count + cost_estimate）
  - **e2e_issues**：四态 issue 跟踪（signature 去重 + occurrence_count + first_seen_at/last_seen_at + resolved_at + CHECK 约束 severity ∈ {info,warning,error} + CHECK 约束 status ∈ {pending,fixed,intermittent,ignored}）
- 索引循环追加 3 条 F062 索引：
  - `idx_e2e_report_created ON e2e_test_reports(created_at DESC)`
  - `idx_e2e_issue_status ON e2e_issues(status, dim_code)` 复合索引
  - `idx_e2e_issue_signature ON e2e_issues(signature)` 供 upsert 去重查找
- 文件末尾新增 **8 个 F062 方法**（独立章节 `v2.3.0-part3-alpha1 F062 端到端健康测试 Agent`）：
  - 路由自省：`register_endpoint` UPSERT 语义 / `get_endpoint_registry` 全读 / `update_endpoint_last_tested` 打时间戳
  - 报告读写：`save_e2e_test_report` 白名单字段 + JSON 自动序列化 / `get_latest_e2e_test_report` 瘦身（不含 full_report_json） / `get_e2e_test_report_detail` 完整
  - issue 四态：`upsert_e2e_issue` 按 signature 合并 pending/intermittent 老记录（fixed/ignored 时新插一条实现回归检测）+ **偶发升级逻辑**（intermittent 状态下 `last_seen_at - first_seen_at ≤ 7 天` 且 `occurrence_count > 5` → 自动升级回 pending） / `set_e2e_issue_status` 四态切换（白名单校验 + fixed/ignored 自动落 resolved_at）
- 类级常量 `E2E_INTERMITTENT_WINDOW_DAYS = 7` / `E2E_INTERMITTENT_UPGRADE_THRESHOLD = 5`（偶发升级阈值，对话 2 可按需覆盖）

**scripts/static_analyzer.py（新建，645 行）**

- F062 维度 ③ Prompt 调用一致性 / ④ 字段契约 / ⑥ 代码异味三个维度的纯 AST 静态规则库
- 零第三方依赖（仅 ast / pathlib / re / json / os 标准库）
- 零 DB 写入、零 AI 调用，只读副作用，单文件扫描复杂度 O(节点数)
- 对外接口（对话 2 e2e_tester 顶层 import 调用）：
  - `scan_prompt_call_consistency(script_paths)` → 维度③ 规则扫描
  - `scan_field_contract(script_paths, db_schema_snapshot)` → 维度④ 规则扫描
  - `scan_code_smells(script_paths)` → 维度⑥ 规则扫描
  - `run_static_scan(script_paths, db_schema_snapshot)` → 一次跑完三个维度 → `{dim3, dim4, dim6, scanned_files, signature_set}`
- Issue 记录结构 1:1 对齐 `db.upsert_e2e_issue`：`{dim_code, severity, endpoint:None, signature, rule_id, detail:{file, line, snippet, msg}}`
- 维度③ 规则清单（4 条）：
  - `smell_prompt_try_import`（warning）：`try: from ... import PROMPT except: ...`
  - `smell_prompt_except_none`（error）：except 分支 `PROMPT = None` 赋值
  - `prompt_wrong_key`（error）：`PROMPT['system']`/`PROMPT['user']`/其他白名单外 key
  - `smell_dead_none_guard`（warning）：`if not PROMPT:` / `PROMPT is None` / `PROMPT == None`
- 维度④ 规则清单（1 条）：
  - `field_unknown`（warning）：`kp.get('xxx')`/`kp['xxx']` 字段不在白名单 + db_schema 列名
- 维度⑥ 规则清单（3 条）：
  - `smell_try_except_none_import`（warning）：通用版 try import + except X=None（非 PROMPT）
  - `smell_silent_except`（warning）：`except: pass` / `except Exception: pass`
  - `smell_except_print_only`（info）：except 只有 print 无 log
- CLI 调试入口：`python scripts/static_analyzer.py [file1.py file2.py ...]`，打印三维度 issue 列表

### Changed

- `00_项目全景.md`：
  - 当前状态升到 v2.3.0-part3-alpha1
  - 数据流追加"E2E 测试"段落
  - 模块状态"5 端到端测试"从"规划"改为"🚧 进行中（对话 1/3 基础层 ✅）"
  - 迭代路线新增 v2.3.0-part3-alpha1/alpha2/正式版三行
  - 新增"F062 设计决策已锁定"章节 + 3 对话拆分表 + 对话 1 交付物清单 + 对话 2 预告
- `01_工程手册.md`：
  - 代码文件清单 db_manager.py / prompt_templates.py 版本号升 v2.3.0-part3-alpha1
  - 新增 `scripts/static_analyzer.py` 高频修改行
  - 规划中文件表 e2e_tester.py 进入"对话 2"
  - 技术踩坑表追加 7 条 F062 踩坑/立规则
  - 末尾新增大章节"v2.3.0 Part3（F062）设计锁定"（设计决策 / 3 对话拆分 / 3 张表 schema / 8 方法签名 / E2E_RESPONSE_JUDGE_PROMPT 双 key 契约 / static_analyzer 维度③④⑥ 规则库 / F062 六维度扫描逻辑 / 对话 1 关卡清单 / F062 与 F048 的口径对齐表）
- `03_Prompt手册.md`：
  - 当前版本升到 v2.3.0-part3-alpha1
  - F062 类从"待开发"升到"已落地"
  - 共享策略块表追加 F062 注入列
  - 新增"F062 E2E_RESPONSE_JUDGE_PROMPT 正式版文本"完整章节
  - 调用位置对照表追加 E2E_RESPONSE_JUDGE_PROMPT 一行
- `README.md`：
  - 顶部版本号升到 v2.3.0-part3-alpha1
  - 新增"v2.3.0-part3-alpha1 本次交付内容"章节
  - 目录结构新增 `scripts/static_analyzer.py` 一行
  - 技术栈 SQLite 表数改为 21 张
  - 关键约束追加 F062 4 条立规则

### 立规则（写入 01 工程手册 + README）

1. **F062 severity 严格对齐 operation_events CHECK**：用 `info`/`warning`/`error`，禁 `warn` 简写。跨功能复用时不能走样
2. **F062 e2e_issues.status 四态 CHECK 强约束**：白名单 `pending`/`fixed`/`intermittent`/`ignored` 在 CREATE TABLE 就打 CHECK，Python 层 + SQL 层双重兜底
3. **偶发升级触发时机**：判断放在 `upsert_e2e_issue` 内部而非定时任务，保持"只在扫描触发时算"的简洁；阈值常量作为类级变量方便覆盖
4. **e2e_issues 已 fixed/ignored 的 signature 回归检测**：upsert 时只合并 pending/intermittent 老记录；fixed/ignored 历史档案不被回退性覆盖，回归问题作为新 pending 独立存在
5. **static_analyzer 保持"宁可多告警"的敏锐度**：已知合理项由对话 2 引擎层白名单二次过滤，不允许反向放宽静态规则
6. **api_endpoint_registry.endpoint 作为 TEXT PRIMARY KEY**：多 methods 合成逗号分隔字符串，不拆条；first_seen_at 永不更新作为"新端点发现"的唯一锚点

### 测试验证

在 Claude 工作区验证通过：

```
python -m py_compile db_manager.py prompt_templates.py static_analyzer.py
→ 全部 COMPILE_OK
```

SQLite 实跑 init_tables 后：`SELECT name FROM sqlite_master WHERE type='table'` 返回 21 张业务表 + sqlite_sequence；`SELECT name FROM sqlite_master WHERE type='index'` 返回 24 条索引，含 3 条 F062 索引。

db_manager 8 个新方法 smoke test（register_endpoint UPSERT / upsert_e2e_issue 合并 / fixed 后回归新插 / intermittent 偶发升级 / set_e2e_issue_status 白名单兜底）全部通过。

prompt_templates `from prompt_templates import E2E_RESPONSE_JUDGE_PROMPT` 顶层 import 成功；双 key 齐全；system_prompt 长度 1834 字符；user_prompt_template 长度 242 字符；6 个占位符齐全。

static_analyzer 扫 mock 含 4 类 bug 的测试文件：精确扫出 11 条 signature，4 类模式全部命中（try import Prompt / except PROMPT=None / if not PROMPT / PROMPT is None / PROMPT['system']/['user']/['content']/except:pass/except:print）。

扫 prompt_templates.py 本身：0 告警（干净）。
扫 db_manager.py：55 条维度④ warning + 6 条维度⑥ warning —— 均为存量合理使用，已留决策给对话 2"已知合理项白名单"二次过滤。

### 对话 1 遗留决策（给对话 2）

- 维度④ 55 条 / 维度⑥ 6 条 db_manager 老代码误报 → 对话 2 在引擎层实现"已知合理 pass 白名单"二次过滤，按 signature 或 `{file:line}` ignore；**不允许**对话 2 反向改弱 static_analyzer 规则宽度
- 对话 2 新建 `e2e_tester.py` 时需：
  - 顶层 `from scripts.prompts.prompt_templates import E2E_RESPONSE_JUDGE_PROMPT` 一行 import（禁 try/except）
  - Flask 路由自省通过 `from scripts.api_server import app; app.url_map.iter_rules()` 实现
  - V3 调用封装借鉴 health_checker 的 `_do_call` 五方法适配器 + 两签名降级
  - 六维度 progress_callback stage 取值表在对话 2 锁定（对齐 F048 模式）
  - `db_schema_snapshot` 通过 PRAGMA table_info 构造后传给 static_analyzer.scan_field_contract

### 老唐操作清单（对话 1 交付）

⚠️ **本次为基础层，不要在本机升级数据库**。对话 2/3 落地前，3 张新表只会是空壳无功能。

1. **替换 3 个代码文件**（到 GitHub 仓库）：`scripts/db_manager.py` / `scripts/prompts/prompt_templates.py` / `scripts/static_analyzer.py`（新建）
2. **推送 GitHub**（Summary：`v2.3.0-part3-alpha1: F062 基础层 - prompt + db + static_analyzer 三件套`）
3. **更新 Claude Projects**：5 个项目文件全量替换（00 / 01 / 02 / 03 / README）+ CHANGELOG
4. **新开对话**：开始对话 2/3 引擎层 e2e_tester.py 开发

### 验证清单（可选，不强制跑）

- [ ] `python -c "from scripts.prompts.prompt_templates import E2E_RESPONSE_JUDGE_PROMPT; print(list(E2E_RESPONSE_JUDGE_PROMPT.keys()))"` 输出 `['system_prompt', 'user_prompt_template']`
- [ ] `python -c "import scripts.static_analyzer as sa; print(sa.__doc__[:40])"` 能打印 docstring 头部
- [ ] GitHub 推送后仓库有 `scripts/static_analyzer.py` 新文件；其他两个文件的 git diff 只在预期范围内

---

## [v2.3.0-part2.1] - 2026-04-22 (hotfix)

**定位**：建表单一来源修复 + migrate 脚本退役，彻底清理"新电脑首次部署"路径。

### 根因

v2.3.0-part2 开发期间，`health_reports` 和 `polish_suggestions` 两张 F048 专用表只在 `scripts/migrate_v230_part2.py` 里建表，没有同步回填到 `db_manager.init_tables()`。`setup.py` 的版本号也停留在 v2.2.0，打印文案"15张表已创建"和实际建出的 16 张不一致，完整 schema 需要 18 张。

**后果**：新电脑跑首次安装.bat → setup.py → init_tables() → 只建 16 张表，缺 health_reports / polish_suggestions → 体检功能调用时直接炸。老唐本机因当时手动跑过 migrate_v230_part2.py 所以未暴露。

### 修复

**scripts/db_manager.py（v2.3.0-part2 → v2.3.0-part2.1）**

- `init_tables()` 在 operation_events 建表之后、索引循环之前，追加两张 F048 表的 `CREATE TABLE IF NOT EXISTS`（SQL 严格复用 migrate_v230_part2.py 版本）
- 索引循环追加 3 个 F048 索引：
  - `idx_health_created ON health_reports(created_at DESC)`
  - `idx_polish_report ON polish_suggestions(report_id)`
  - `idx_polish_status ON polish_suggestions(status)`
- 文件头注释里两处"建表由 migrate_v230_part2.py 完成"改为"v2.3.0-part2.1 起由 init_tables 直接建"
- F048 区块起始注释"两张表由 migrate_v230_part2.py 建"改为"由 init_tables() 建"
- 验证：用全新 sqlite 库跑 init_tables 后 `sqlite_master` 查出 18 张业务表 + 21 个索引，health_reports / polish_suggestions / 3 个 F048 索引全部在

**scripts/setup.py（v2.2.0 → v2.3.0-part2.1）**

- 顶部版本号 `v2.2.0` → `v2.3.0-part2.1`
- `get_version()` 兜底返回值 `"2.2.0"` → `"2.3.0-part2.1"`
- 打印文案 `"OK 15张表已创建"` → `"OK 18张表已创建"`
- 头部文档注释新增 v2.3.0-part2.1 变更说明段（说明 init_tables 已吸收所有 migrate 逻辑）

**删除**

- `scripts/migrate_v223.py`（v2.2.3 schema 迁移脚本，历史使命完成；相关字段 truncation_count / recovery_runs / last_recovery_at / qa_source 已全部在 init_tables 的 source_files / knowledge_points 建表 SQL 内）
- `scripts/migrate_v230_part2.py`（v2.3.0-part2 schema 迁移脚本，历史使命完成；两张表 + 3 索引已全部回填到 init_tables）

### 不变

- `首次安装.bat` 一字未改（它本来就调 setup.py → init_tables，升级 init_tables 后自动覆盖 18 张表）
- 数据库已存在的老用户零风险：`CREATE TABLE IF NOT EXISTS` 对已存在表是 no-op，重跑 setup.py 不会破坏数据
- 其他代码文件（api_server / health_checker / extractor 等）全部不动

### 经验教训（写入工程手册"技术踩坑"）

**schema 单一来源原则**：`init_tables()` 必须是唯一的建表真相。任何 schema 变更都要同步改 init_tables()，migrate 脚本只服务"已部署老库的一次性追赶"，一旦所有老库都升完就必须退役（代码删除 + setup.py 吸收）。绝对不能让 init_tables 长期落后于 migrate 脚本——否则新电脑首次部署必然缺表。

### Docs

- `00_项目全景.md`：当前状态版本升至 v2.3.0-part2.1；迭代路线表新增 v2.3.0-part2.1 行；待办需求新增"v2.3.0-part2.1 hotfix 已完成"小节
- `01_工程手册.md`：db_manager.py 版本号升至 v2.3.0-part2.1；首次安装.bat 描述去掉"待改造"；技术踩坑表新增"schema 单一来源原则"；代码约定表替换旧 migrate_v223 约定为新 schema 规则；health_reports / polish_suggestions 建表来源描述改为 init_tables
- `README.md`：顶部版本号升至 v2.3.0-part2.1；目录结构删除 migrate_v223.py 和 migrate_v230_part2.py 两行；技术栈 SQLite 描述更新；迭代路线新增 v2.3.0-part2.1 行
- `CHANGELOG.md`：本条目
- 02_知识体系.md / 03_Prompt手册.md：本次不动

### 老唐操作清单（4 步）

1. **替换 2 个代码文件**：`scripts/db_manager.py` / `scripts/setup.py`
2. **删除 2 个文件**：`scripts/migrate_v223.py` / `scripts/migrate_v230_part2.py`
3. **推送 GitHub**（Summary: `v2.3.0-part2.1: schema 单一来源修复 + migrate 脚本退役`）
4. **新电脑验证**：在新电脑上 clone 仓库 → 双击 `首次安装.bat` → 一键建完 18 张表

### 验证清单

- [ ] 新电脑跑完首次安装.bat，SQLite 库查询 `SELECT name FROM sqlite_master WHERE type='table'` 返回 18 张业务表（含 health_reports / polish_suggestions）
- [ ] 启动后台 → Tab 2 → 工具箱 → 第 10 张"知识库体检"卡点击无报错
- [ ] 30 条档位试跑一次体检，能完成并产出报告
- [ ] scripts 目录下**不存在** migrate_v223.py 和 migrate_v230_part2.py
- [ ] 老电脑零感知：现有数据完好，原有功能全部正常

---

## [v2.3.0-part2] - 2026-04-22

### F048 知识库体检 Agent - 界面层前端正式版(对话3/3 后半部分) 三对话闭环完成

**v2.3.0-part2 = v2.3.0-part2-beta1 + review.html 前端。后端 8 路由在 beta1 已交付并稳定,本轮 review.html 前端完整落地。**

### Added

- **web/templates/review.html(+603 行,2089→2692)—— F048 界面层前端**
  - 工具箱 grid 尾部插入第 10 张卡 `tc-health`(紫色 H 图标,`onclick="runTool('health')"`)
  - 新增 3 个模态框:
    - `#healthStartDlg`(560px 宽):档位选择,5 个大按钮(30/50/100/200/不限),每档显示预计时间(约 10/17/35/70 分钟 / 按库容估),50 条用 `.default-option` 样式视觉引导。底部"历史报告"按钮穿透到 toolResult 列表
    - `#healthReportDlg`(760px 宽):报告详情,总分大字 + 对比上次趋势 + 六维度 2×3 卡(健康25/结构10/加工20/关联10/打磨20/变现15 权重)+ 变现场景 5 项分数条(含 gap 提示)+ 优先喂料方向(有序列表)+ 底部"开始 Review"按钮
    - `#healthReviewDlg`(820px 宽):逐条 Review,顶部 N/总数指针 + tier 徽章(L1/L2/L3) + suggestion_type 徽章(含 enrich 青/merge 橙扩展)+ diagnosis `<details>` 折叠 + 左右对比(review-compare) + drop/split/L3_manual 各自彩色提示框 + polish_notes 提示 + 动态按钮区
  - 新增 13 个 F048 JS 函数(严格 ES5,无箭头函数/模板字符串/async/await/const/let/emoji,Node `--check` 语法通过):
    - `doHealthStart(polishMax)` — 关弹窗 POST `/api/tools/health/start` 成功调 showTaskProgress+startPolling,"none" 转 null
    - `openHealthHistory()` / `loadHealthHistory()` — GET `/api/tools/health/history?limit=50` 在 toolResult 展示历史列表(时间/状态/总分/条数),点击行直接 `openHealthReport(report_id)`
    - `openHealthReport(reportId)` / `renderHealthReport(r)` / `renderDimCard(name, dim, weight)` — GET `/api/tools/health/report/<rid>` 拉完整报告,full_report_json 已由后端自动 parse;渲染总分+六维度卡+变现场景行+喂料方向+趋势对比。renderDimCard 按分数阈值自动染色(≥80 绿/≥60 黄/<60 红)
    - `startHealthReview(reportId)` / `renderHealthReview(items)` — GET `/api/tools/health/suggestions/<rid>` 前端过滤 `status==="pending" || "manual_review_needed"`,按 tier+suggestion_type 渲染 4 分支按钮矩阵
    - `_renderReviewSide(title, kpTitle, data, isPolished)` 辅助函数 — 左右对比单侧卡渲染,按 8 条固定映射(title/description/practical_insights/tags 三层),不按 content_type 分流
    - `healthReviewNext()` / `healthReviewPrev()` — 纯前端指针移动,不发请求
    - `healthAdoptCurrent()` — POST `/api/tools/health/suggestions/<sid>/adopt`,成功后本地 splice 列表,split 场景 setTimeout 多弹一次 split_note toast
    - `healthRejectCurrent()` — POST `/api/tools/health/suggestions/<sid>/reject` 带 `{reason:""}`
    - `healthDropCurrent()` — showConfirm → POST `/api/tools/health/suggestions/<sid>/drop`,error 时附加 step 标识
  - 新增 3 个状态变量:`_healthReviewList / _healthReviewIdx / _healthReportId`(F048 Review 流程游标)
  - **checkRunningTask titles 字典追加 `"health":"知识库体检进行中"`**(与 api_server.py 第 2254 行 `_task["type"]="health"` 对齐,不是 `"health_check"`)
  - **showTaskProgress 和 startPolling 的按钮禁用/恢复列表追加 `"tc-health"`**
  - **startPolling 完成分支新增 `if (r.type === "health" && r.result && r.result.success)`** 弹 showConfirm"体检完成,总分 XX,是否立即查看报告?",确认后调 `openHealthReport(r.result.report_id)`
  - runTool 追加 `"health"` 分支:先 GET `/api/tools/health/latest` 探最新报告,有则在 toolResult 展示"最近一次 总分 XX / 扫描 XX 条"+ 三按钮(查看报告/开始新体检/历史报告),无则直接打开档位弹窗
  - CSS 新增(约 85 行):
    - tier 三色边框(`.tier-L1` 绿 #52c41a / `.tier-L2` 黄 #faad14 + 背景 #FFFBEF / `.tier-L3` 灰 #8c8c8c + 背景 #F5F5F7)
    - tier 徽章三色 + suggestion_type 徽章六色(drop 红 / split 蓝 / improve 紫 / manual 灰 / enrich 青 / merge 橙)
    - 六维度 grid(2×3,顶部彩条按 good/mid/bad 染色)
    - 总分大字 `.health-total` + `.ht-num`(48px primary 色)
    - `.monetize-section` + `.monetize-row`(五项分数条 + gap 提示)
    - `.feed-section`(喂料方向 primary 色调色块)
    - `.review-compare`(左右对比 grid)+ `.review-side`(单侧卡)+ `.review-side.polished`(打磨侧 primary-soft 边框)+ `.rs-tag`(标签 pill)+ `.rs-insight`(举一反三卡)
    - `.review-diag <details>`(诊断折叠)
    - `.review-actions`(上一条 + 动态按钮矩阵)
    - `.tier-option`(档位大按钮)+ `.tier-option.default-option`(50 条默认项视觉突出)
    - `.history-item`(历史列表行)
  - Header 版本号 v2.3.0-part1 → v2.3.0-part2(含 `<title>` 标签)

### Fixed

- **`_task["type"]` 前后端口径对齐修正**:v2.3.0-part2-beta1 及之前的项目文件(01 工程手册 / CHANGELOG beta1 / 03 Prompt 手册)里把口径误写成 `"health_check"`,但 api_server.py 第 2254 行实装为 `"health"`。v2.3.0-part2 正式版前端按代码实装为准,同步修正项目文件所有误标的 `"health_check"` 口径(仅指 `_task["type"]` 场景;`health_check_start` 等事件名和 `health_checker.py` 文件名是合规命名,不受影响)
- **CHANGELOG beta1 条目里"正式版 v2.3.0-part2"草稿 Added 段路由名错误修正**:原草稿写的 `/api/tools/health/reports` / `/api/tools/health/reports/<report_id>` / `/api/tools/health/reports/<report_id>/suggestions` 是 beta1 交付前的早期命名;后端 beta1 实际实装的正确路由为 `/api/tools/health/history` / `/api/tools/health/report/<rid>` / `/api/tools/health/suggestions/<rid>`。本条目按真实后端契约重写

### Design Locked (正式版补充设计决策)

- **前端"先探再弹"交互流**:runTool('health') 先 GET /latest,有历史报告就展示"最近一次"提示+三按钮(查看/开始新体检/历史),无则直接弹档位。理由:避免老唐每次都要先看档位弹窗才知道上次得了多少分,"上次总分看一眼"是最高频信号
- **_renderReviewSide 辅助函数提取**:原设计要求 13 函数固定清单,实装时发现左右对比卡渲染逻辑相同(70 行标题+描述+insights+标签三层),提取为 `_renderReviewSide(title, kpTitle, data, isPolished)` 共享,`isPolished` 控制:(1) 打磨侧单独展示 description 作为"polished_description 预览" (2) 打磨侧卡片底色 .polished + primary 色标题。不计入 13 函数列表,属辅助内部函数
- **采纳/驳回/删除后本地 splice 不重新请求**:三种成功操作直接 `_healthReviewList.splice(_healthReviewIdx, 1)` 后 renderHealthReview,指针不动自然显示下一条。与后端 100% 无状态,老唐误刷浏览器可重新请求 /suggestions 加载剩余 pending,不会误操作已处理条目
- **略过按钮纯前端**:healthReviewNext() 只做指针 +1,不 splice,允许"上一条"回退重看;与 adopt/reject/drop 的 splice 语义不同
- **suggestion_type 徽章新增 enrich 青 / merge 橙两色**:除工程手册原列 4 色(drop 红/split 蓝/improve 紫/manual 灰)外,实装补 enrich/merge 两色,覆盖 HealthChecker 所有 `suggestion_type` 取值(`improve/enrich/split/merge/drop/manual_review` 共 6 种)。未来引擎层新增类型只需补 `.badge-XXX` CSS 即可,不改 JS

### Not Implemented (本版本不做)

- 批量重算成熟度按钮:工具箱第 11 卡位口头约定,计划 v2.3.1 单独交付;本版本工具箱仍是 10 张卡
- 历史体检趋势图:/report/<rid> 响应里 full_report_json 可含 `prev_comparison.diff` 供前端渲染"对比上次 +X 分"文字,折线图等规划 v2.3.1
- /adopt 三步失败回滚:SQLite 本地单库事务 API 未暴露,任一失败硬 500 + step 标识,不做 rollback(与 dup_merge / batch_rerun 保持一致硬失败风格)

### Logging (埋点延续)

- api_server F048 8 路由在 beta1 已接入事件埋点(`health_suggestion_adopted` / `health_suggestion_dropped` / `health_suggestion_rejected`);本轮前端仅消费 API 响应,不产生新事件
- operation_hook("health_adopt") 自动写 backup_trigger / backup_failed(v2.2.3 既有机制)

### Docs

- `00_项目全景.md`:当前状态版本从 v2.3.0-part2-beta1 升至 v2.3.0-part2 正式版;3 对话拆分进度表"对话 3 前端"打 ✅;模块 4 ✅ 文字"基础层+引擎层+界面层后端+前端全部闭环";迭代路线表 v2.3.0-part2 行从"进行中"改为"已交付 正式版 2026-04-22";关键决策第 7 点新增前端契约锁定(含 `_task["type"]="health"` 显式标注)
- `01_工程手册.md`:api_server.py 版本号 v2.3.0-part2-beta1 → v2.3.0-part2 并追加 `_task["type"]="health"` 标识;review.html 版本号 v2.3.0-part1 → v2.3.0-part2 并补完整功能列表;技术踩坑表追加 7 条 v2.3.0-part2 正式版踩坑(含 `_task["type"]` 口径修正 / _renderReviewSide 辅助函数提取 / 左右对比不分流 / 按钮矩阵 4 分支 / 本地 splice / default-option 视觉引导);前端改动速查段内 `health_check` → `health` 口径纠正
- `03_Prompt手册.md`:顶部注释行 + F048 小节标题 + 调用位置表措辞从"前端下一轮"升为"前端已落地 v2.3.0-part2 正式版";口径 `health_check` → `health` 同步修正(若有引用 _task type 场景)
- `README.md`:版本号 v2.3.0-part2 口径复核通过(beta1 时已预写至此口径);本次交付内容段落再校准
- `CHANGELOG.md`:本条目(重写正式版 Added 段,修正 beta1 草稿的 `/reports/<id>` → `/history` + `/report/<rid>` + `/suggestions/<rid>` 路由名错误 + `health_check` → `health` 口径错误)

### Compat (向下兼容)

- /api/tools/duplicate-scan / /api/tools/duplicate-reset-rescan / /api/tools/qa-backfill 等历史接口保留不变
- 浏览器缓存的旧版 review.html 不会因 F048 新增路由受影响(工具箱缺"知识库体检"卡,其他功能正常);强制刷新(Ctrl+F5)即可加载新 UI
- 数据库 schema 无本次前端对话变更;alpha1 新增的 health_reports / polish_suggestions 两表合计 18 张

### 老唐操作清单(5 步)

1. **备份数据库**:启动后台 → 一键备份(或手动复制 data/database/knowledge_base.db)
2. **替换 1 个代码文件**:`web/templates/review.html`(api_server.py / db_manager.py / health_checker.py 本轮不改动)
3. **重启服务**:关闭 `启动后台.bat` 后重开;浏览器访问管理后台后**强制刷新(Ctrl+F5)**清掉缓存的旧 review.html
4. **首次体检**:Tab 2 系统管理 → 工具箱 → 点击第 10 张"知识库体检"紫色 H 卡 → 选 **30 条档位**(首次试水约 10 分钟)→ 等待完成弹 confirm"是否立即查看报告?"
5. **Review 一轮**:报告弹窗查看六维度分数 → 点"开始 Review" → 逐条决策(采纳 / 驳回 / 略过 / 确认删除)

### 验证清单(回归测试要点)

- [ ] 工具箱末尾出现第 10 张紫色"知识库体检"卡,点击后若无历史报告直接弹档位,有则展示"最近一次"三按钮
- [ ] 档位弹窗 5 个选项(30/50/100/200/不限),50 条档有绿色边框视觉突出,每档下方显示预计时间
- [ ] 点击 30 条档,Toast"体检已启动"+ 进度条区显示"知识库体检(30 条)"+ tc-health/tc-preprocess/tc-extract/tc-reextract/tc-batchRerun 五个按钮禁用
- [ ] 刷新页面进度条不丢,taskTitle 显示"知识库体检进行中"(checkRunningTask titles 命中 `"health"`)
- [ ] 完成弹 confirm"体检完成,总分 XX,是否立即查看报告?",点确认打开 healthReportDlg
- [ ] 报告详情:总分大字 + 六维度 2×3 卡(按分数自动染色)+ 变现场景 5 项分数条(有 gap 时显示"缺: XXX")+ 喂料方向有序列表 + 对比上次"↑/↓/→ X 分"
- [ ] 点"开始 Review",显示 healthReviewDlg,tier 徽章+suggestion_type 徽章并排显示
- [ ] L1 improve 卡显示"采纳 + 驳回 + 略过"三按钮;L1 split 卡显示"采纳第 1 条 + 驳回 + 略过"+ 蓝色提示框;L1 drop 卡显示"确认删除(红) + 驳回 + 略过"+ 红色提示框;L2 improve 卡同 L1 improve;L3_manual 卡只显示"驳回 + 略过"+ 灰色提示框(无采纳)
- [ ] 诊断详情默认折叠,点击 `<summary>` 展开显示原诊断文本
- [ ] 左右对比卡:原文侧"原文"灰底 + 打磨侧"打磨稿"primary-soft 边框;两侧都有标题/举一反三/三层标签;打磨侧额外显示"描述预览 (polished_description)"
- [ ] 采纳成功:Toast"已采纳(X 个字段更新)"; split 场景额外 Toast 提示其余条需手动处理; 列表 splice 指针不动自然显示下一条
- [ ] drop 场景点"确认删除"先弹 showConfirm,确认后 Toast"已删除 (kp#X → ignored)";到 Tab 1"已忽略"筛选能找到
- [ ] 略过按钮:F12 Network 核验不发请求,指针 +1 显示下一条;"上一条"按钮可回退
- [ ] Review 走到最后一条之后显示"本轮 Review 完成"+ 条数统计
- [ ] L3_manual 手动 `curl -X POST /api/tools/health/suggestions/<sid>/adopt` 返回 400(后端兜底,前端已不显示采纳按钮)
- [ ] 历史报告:工具箱 runTool('health') 后三按钮之一"历史报告"或档位弹窗底部"历史报告",展示 50 条历史列表,点击跳报告详情

### Not Changed (本次对话不改)

- `scripts/api_server.py` — beta1 已就绪,前端只消费 8 路由
- `scripts/db_manager.py` — alpha1 已就绪,前端间接通过 api_server 读
- `scripts/health_checker.py` — alpha2 已就绪,前端不直接调
- `scripts/prompts/prompt_templates.py` — alpha1 已就绪,前端不碰 Prompt
- `scripts/backup_manager.py` — operation_hook 复用,无需改动
- `scripts/migrate_v230_part2.py` — alpha1 已跑过,schema 无变更

---

## [v2.3.0-part2-beta1] - 2026-04-22
 
### F048 知识库体检 Agent - 界面层后端(对话3/3 前半部分)
 
**新增路由(`scripts/api_server.py` +667 行,2049→2716)**
 
- `GET  /api/tools/health/latest` — 工具箱卡片用:最新一份 completed 报告瘦身摘要(不含 full_report_json 省带宽)
- `POST /api/tools/health/start` — 启动全库体检(后台线程,`_task` 单例互斥;polish_max 白名单 30/50/100/200/null)
- `GET  /api/tools/health/history` — 历史报告列表(query limit 1-200,默认 20)
- `GET  /api/tools/health/report/<rid>` — 单份完整报告(含 full_report_json 自动 parse)
- `GET  /api/tools/health/suggestions/<rid>` — 该报告的 Review 清单(附加 `kp_current_title` + `kp_current_status`,kp 已删除时 status=deleted)
- `POST /api/tools/health/suggestions/<sid>/adopt` — L1/L2 采纳(三步原子:备份→update_kp→apply;任一步失败 500 附 step 标识;split 只取 sc[0]+split_note;L3_manual 返 400;drop 类型返 400 提示改走 /drop)
- `POST /api/tools/health/suggestions/<sid>/drop` — drop 独立路由(走 `ignore_knowledge_point(kp_id, reason="health_drop: "+diagnosis[:200])`)
- `POST /api/tools/health/suggestions/<sid>/reject` — 驳回(仅改 status=rejected,允许后续重入候选池)
 
**新增辅助函数(api_server 模块级内联实装)**
 
- `_get_suggestion_by_id(sid)` — 按 sid 查单条 polish_suggestion(db_manager 不回改,本地 10 行 SQL 解决)
- `_merge_ai_content(kp_row, sc)` — 固定 8 条映射路径(**不按 content_type 分流**):
  1. `sc.title` → `kw.title` 直接覆盖
  2. `sc.practical_insights` → `kw.practical_insights` 直接覆盖 list
  3. `sc.tags.layer1` → `kw.final_category_tags`(list,仅非空覆盖)
  4. `sc.tags.layer2` → `kw.final_attribute_tags`(dict,仅非空覆盖)
  5. `sc.tags.layer3` → `kw.final_keywords`(list,仅非空覆盖)
  6. `sc.description` → `ai_extracted_content.polished_description` **新键**(不覆盖原主字段)
  7. `sc.polish_notes` → `ai_extracted_content.polish_notes` **新键**
  8. `content_readiness` **不传**,保留数据库原值
- `_health_progress_adapter(payload)` — HealthChecker 回调 `{stage, current, total, message}` 映射到 `_task["progress"]`,total_files=8 固定,打磨阶段(dim5_polish)把 current/total 拼进 message 显示"打磨中 X/Y"
 
**事件埋点**
 
- `health_suggestion_adopted` / `health_suggestion_dropped` / `health_suggestion_rejected` 三类结构化事件写入 `operation_events` 表(尽力而为,失败不影响主流程)
 
### Fixed
 
- 无本轮修复项
 
### 注意
 
- **前端 `review.html` 未改动本轮**,F048 工具箱第 10 张卡 + 3 模态框 + 13 JS 函数放下一轮交付,届时才是 v2.3.0-part2 正式版发布节点
- 本轮体检功能在后端侧可通过 API 调用验证(curl / Postman),前端按钮暂无入口
- `_task` 单例互斥意味着体检期间无法启动提取/批量重跑任务(反之亦然,409 保护)
- 体检任务执行时长取决于打磨档位:30 条约 10 分钟 / 50 条约 17 分钟 / 100 条约 35 分钟 / 200 条约 70 分钟

## [v2.3.0-part2-alpha2] - 2026-04-21
 
### Added
 
- **scripts/health_checker.py（新增，~1350 行）—— F048 知识库体检 Agent 引擎层**
  - 六维度扫描：①健康度 ②结构分布 ③加工深度 ④关联密度 ⑤低分打磨 ⑥变现匹配度
  - 三层打磨降级链完整落地：
    - L1 主链：HEALTH_DIAGNOSIS (V3) → HEALTH_POLISH (R1) → HEALTH_POLISH_VERIFY (V3)
    - L2 降级：HEALTH_POLISH_CONSERVATIVE (V3)
    - L3 兜底：规则标记 `status='manual_review_needed'`，`suggested_content=None`
  - 降级触发条件严格对齐 03_Prompt 手册契约：
    - 诊断阶段：`recommend_manual_review=true` 或 `polish_difficulty=impossible` → 直接 L3
    - 诊断阶段：`polish_direction=drop` → 生成 drop 建议（tier=L1）不走 R1
    - 主链校验：`verify_pass=false` / `re_score<原分` / `confidence=low` / R1 截断 → 降 L2
    - L2 失败 → L3
  - 单次打磨档位白名单：`POLISH_MAX_OPTIONS = [30, 50, 100, 200, None]`，默认 50
  - 六维度权重：健康 0.25 / 结构 0.10 / 加工 0.20 / 关联 0.10 / 打磨 0.20 / 变现 0.15（总和 1.0）
  - 进度回调复用 extractor 的 `progress_callback` 模式，stage 取值 9 种（init/dim1/dim2/dim3/dim4_island/dim5_polish/dim6_monetize/done/failed）
  - 维度隔离：`_safe_dim()` 统一包装，任一维度异常不中断整体，失败返回 score=0
  - 孤岛精判抽样外推：候选超 50 条时按比例外推估算全库孤岛率，避免逐条调 V3
  - 成本估算：按 V3/R1 token 单价累计 `cost_estimate` 写入 `health_reports`
  - AI 调用封装：`_do_call()` 多候选方法名适配（call_chat/chat/complete/call/generate），兼容 deepseek_client 不同签名
  - 模块级便捷函数：`run_health_check(db, client, progress_callback, polish_max)` 供 api_server 简短调用
### Design Locked (决策锁定)
 
- **单次打磨默认 50 条**：瓶颈在老唐 Review 不在 AI 生成；50 条约 17 分钟生成 + 半天 Review，匹配"加工一批→体检一次→Review 一批"节奏
- **打磨得分不奖励"成功数"**：`max(0, 100 - 低分占比×100)`，避免激励"多生产低分去打磨赚分数"反激励
- **R1 打磨失败不做 F057 截断补救**：三层降级链本就是兜底，重提翻倍成本+超时风险
- **采纳事务边界不下沉 db 层**：`db.apply_polish_suggestion` 只改 status；`update_knowledge_point` 由 api_server 层在 `operation_hook("health_adopt")` 之后调用，保持"备份→更新 kp→标记 applied"三步清晰可见
### Logging (埋点新增)
 
health_checker.py 接入 `operation_events` 表的事件类型（10 种）：
 
| event_type | severity | 触发时机 |
|-----------|---------|---------|
| health_check_start | info | 开始体检 |
| health_check_done | info | 完成 |
| health_check_failed | error | 整体异常 |
| health_check_param_invalid | warn | polish_max 非白名单值自动兜底 |
| health_dim_failed | warn | 单维度异常隔离 |
| health_ai_call_failed | warn | V3/R1 调用失败 |
| health_polish_fallback | info | 单条打磨降级 L1→L2 |
| health_polish_l3_manual | info | 单条进入 L3 |
| health_polish_save_failed | error | suggestion 落盘失败 |
| health_internal_call_failed | warn | 内部 DB 调用异常 |
 
### Docs
 
- `00_项目全景.md`：版本升到 v2.3.0-part2-alpha2，模块 4 状态更新为"基础层+引擎层已交付"，迭代路线新增 alpha2 条目，设计锁定新增"单次打磨档位"和"六维度权重"
- `01_工程手册.md`：代码清单新增 `health_checker.py` 条目；新增 9 条技术踩坑（维度隔离约束、R1 不做补救、AI 客户端多候选、字段命名对齐、孤岛抽样外推、打磨不奖励成功数等）；新增"v2.3.0-part2-alpha2 关键设计决策"表（8 条）；新增"health_checker.py 结构速查"和"stage 取值"和"事件埋点"章节
- `03_Prompt手册.md`：6 个体检 Prompt 的"调用位置"列从"对话2 待开发"更新为"✅ 已落地"；F048 降级链说明从"Prompt 契约已落地"升级为"引擎层调用接入 ✅ 已落地"
### Not Changed (本次对话不改)
 
- `scripts/db_manager.py` — 基础层 alpha1 已就绪，引擎层只读不写
- `scripts/prompt_templates.py` — 基础层 alpha1 已就绪，引擎层只读
- `scripts/backup_manager.py` — 对话 3 才会调 `operation_hook("health_adopt")`，本次不涉及
- `scripts/api_server.py` — 对话 3 开发
- `web/templates/review.html` — 对话 3 开发
### Next (对话 3 预告)
 
- `scripts/api_server.py`：新增 6-8 个路由（`POST /api/tools/health/run` / `GET /api/tools/health/reports` / `GET /api/tools/health/reports/:id` / `POST /api/tools/health/polish/adopt` / `POST /api/tools/health/polish/reject` 等）
- `web/templates/review.html`：工具箱第 10 张卡"知识库体检"+ 档位弹窗（30/50/100/200/不限）+ 体检报告弹窗 + 逐条 Review UI
- 项目文件 00/01/03 + README + CHANGELOG 收尾到 v2.3.0-part2（去掉 alpha 后缀）

## v2.3.0-part2-alpha1 — 2026-04-20

F048 知识库体检 Agent 基础层交付(对话 1/3)。本版本只交付契约与 schema,不包含引擎与界面;完整功能需等对话 2/3 引擎层 health_checker.py 与对话 3/3 界面层 api_server/review.html 落地后才可触发。

### 新增

**prompt_templates.py**
- PROMPT_VERSION 升级 `v2.2.3` → `v2.3.0-part2`
- 新增 6 个 Prompt 契约,Prompt 总数 21 → 27:
  - `HEALTH_DIAGNOSIS_PROMPT` (V3) — 低分知识点病根诊断,输出 root_cause_type / polish_direction / polish_difficulty / recommend_manual_review
  - `HEALTH_POLISH_PROMPT` (R1) — 创造性打磨,保留 DATA_PRECISION_RULE / SELF_CHECK / EXCERPT_REQUIREMENT 硬约束
  - `HEALTH_POLISH_VERIFY_PROMPT` (V3) — 打磨结果校验,判 verify_pass 与 re_score
  - `HEALTH_POLISH_CONSERVATIVE_PROMPT` (V3) — L2 降级保守打磨,严格禁止新增数据/案例/推理衍生
  - `HEALTH_ISLAND_JUDGE_PROMPT` (V3) — 孤岛精判,区分 true_island / niche_topic / duplicate_candidate / structural_isolated / none,避免将独家经验误判为孤岛
  - `HEALTH_MONETIZE_REPORT_PROMPT` (V3) — 变现匹配度报告,对照 5 种变现场景评分

**db_manager.py**
- docstring 升级,表清单 16 → 18(health_reports + polish_suggestions 两张新表)
- 新增 12 个方法,按三组分类:
  - 健康报告读写(5):save_health_report / update_health_report / get_latest_health_report / get_health_report_list / get_health_report_detail
  - 打磨建议读写(4):save_polish_suggestion / get_polish_suggestions_by_report / apply_polish_suggestion / reject_polish_suggestion
  - 扫描候选查询(3):get_kp_for_health_scan / get_polish_candidates / get_island_candidates
- 新增白名单常量 `_HEALTH_REPORT_INSERT_FIELDS` / `_HEALTH_REPORT_UPDATE_FIELDS` / `_POLISH_SUGGESTION_INSERT_FIELDS`,防止任意字段 UPDATE/INSERT
- 新增静态方法 `_safe_json_parse`,处理 JSON 字段序列化/反序列化
- 字段 AS 别名映射(对齐 health_checker 契约):id → kp_id / review_status → status / source_authority → authority_level / access_level → monetize_tier
- JSON 字段自动序列化:save_health_report / save_polish_suggestion 支持直接传 dict,内部自动 `json.dumps`;get 类方法读取时自动 `json.loads`

**migrate_v230_part2.py(新建)**
- 幂等迁移脚本,对齐 migrate_v223.py 风格
- 支持 `--dry-run` 预览 SQL / `--db-path` 自定义路径
- 建两张表(health_reports / polish_suggestions)+ 3 个索引(idx_health_created / idx_polish_report / idx_polish_status)
- 单事务 BEGIN/COMMIT,失败自动 rollback
- 重跑安全:两表均已存在时直接跳过
- 纯 schema 变更,不做数据迁移

### 确认不改动

**backup_manager.py** — 源码第 244-304 行 operation_hook 无 op_name 白名单,任意字符串可接受。对话 3/3 界面层实现"体检采纳"时调用 `operation_hook("health_adopt")` 直接可用,OP_KEEP_PER_NAME=5 自动生效。

### 关键设计约定(后续对话严格遵守)

- **事务边界铁律**:`apply_polish_suggestion` 仅更新 `polish_suggestions.status='applied'` + applied_at,不触 knowledge_points。api_server 层的 `/api/tools/health/polish/adopt` 路由负责三步清晰:备份 → 更新 kp → 标记 suggestion applied,风格对齐 v2.2.3 F061 `_qc_rerun_core`
- **低分候选严格口径**:`(qa_score>0 AND qa_score<=2) OR qa_source='rule_fallback'`,`qa_score>0` 过滤掉"未质检"的 kp(默认值 0.0),避免污染打磨池
- **重入机制**:`apply_polish_suggestion` / `reject_polish_suggestion` 后,对应 kp 可重新进入 `get_polish_candidates()`。NOT EXISTS 只排除 pending 和 manual_review_needed,允许老唐对打磨结果不满意时再次生成建议
- **qa_source 默认值陷阱**:kp 表 `qa_source TEXT DEFAULT 'batch'`(非 NULL)。历史 kp 字段值即为 'batch'。`qa_source='rule_fallback'` 分支只命中真·走过 L3 兜底的 kp,不会误命中历史数据
- **三层打磨降级链**:
  - 主链 L1:V3 诊断 → R1 打磨 → V3 校验
  - 降级条件:verify_pass=false / re_score<原分 / R1 截断 / 格式异常 → L2
  - L2:V3 保守打磨(不创造,只微调)
  - 降级条件:仍失败 → L3
  - L3:规则兜底,`status='manual_review_needed'`,不生成 suggested_content

### 实测验证

串测脚本覆盖:
- health_reports / polish_suggestions 两张表建表 + 3 索引
- 12 个 DB 方法 CRUD 全路径
- `get_polish_candidates` 四种排除场景:pending 挡住 / 未质检 qa_score=0 / 已 confirmed / 实际低分通过
- apply / reject 后的重入机制(kp 能重新进入候选池)
- migrate 脚本 4 路测试:dry-run / 真实执行 / 幂等重跑 / 缺 DB 报错

### 待完成工作

- 对话 2/3(引擎层):新建 scripts/health_checker.py,六维度扫描 + 三层打磨降级链
- 对话 3/3(界面层):api_server 新增 6-8 路由 + review.html 工具箱第 10 张卡 + 逐条 Review UI + CHANGELOG 升级为正式版 `v2.3.0-part2`

### 副作用提示

PROMPT_VERSION 升级后,F044 版本重提取会将所有老 kp 识别为"待升级"状态。但本版本仅新增 6 个体检相关 Prompt(不用于提取),老 kp 无需实际重提取。老唐可忽略仪表盘"待升级"数字,或待后续版本统一处理。

---

## v2.3.0-part1.1 — 2026-04-18 (hotfix)

修复 v2.3.0-part1 引入的 `ImportError: cannot import name 'operation_hook' from scripts.backup_manager` 启动阻塞问题。

### 修复

**backup_manager.py**
- 在文件底部追加 5 行模块级便捷函数 `def operation_hook(op_name): return BackupManager().operation_hook(op_name)`
- BackupManager 类方法完全保留向下兼容
- api_server.py 第 36 行 `from scripts.backup_manager import operation_hook, BackupFailedError` 得以正常 import

### 根因复盘

v2.2.3 初版 backup_manager.py 只在 BackupManager 类里定义了 `def operation_hook(self, op_name)` 类方法,未提供模块级包装函数;但 api_server.py 按工程手册设计用 `from scripts.backup_manager import operation_hook` 这种模块级导入方式,导致 Python 无法在模块 top-level 找到该名字。此前未爆原因是后台从 v2.2.3 交付起一直未完整重启,v2.3.0-part1 全部完成后首次重启才触发。

### 经验教训

对外 import 契约必须在首次交付时就提供模块级包装。凡是其他文件会 `from X import y` 的 y,必须在 X 模块 top-level `def` 或 `class`,不能只定义类方法。

### 不变

api_server.py / review.html / 其他所有代码与数据库 schema 均不变。

---

## v2.3.0-part1 — 2026-04-16

**定位**:仪表盘工具箱整体优化 + 批量重跑与 AI 去重联动 + Step 8 增量重复检测 bug 修正。

### 新增

**F049 仪表盘工具箱优化**
- 合并三种重复检测为单一入口:工具箱的"全库重复检测"和"清理并重扫"两张卡合并为一张"智能重复检测",点击弹出三选一对话框:
  - 最近 7 天(约 2-3 毛)
  - 全库扫描(约 3-5 毛)
  - 彻底重扫(约 5-8 毛,强制备份 + 清 pending + V3 全库重扫)
- 仪表盘新增 3 张标签分布卡:
  - Card 12 业务领域分布(A 组 13 个标签)
  - Card 13 知识形态分布(C 组 9 个标签)
  - Card 14 客户视角分布(D 组 5 个标签)
  - 每张卡默认显示 Top5 dBar + 底部"展开全部 N 个"按钮
  - 所有标签支持点击穿透跳转到审核列表(新增 `layer1_tag` 筛选参数)
- 新增后端接口 `POST /api/tools/duplicate_unified`,请求体 `{mode:"recent"/"full"/"reset_rescan", days?:7}`
- 侧边栏新增一级标签筛选条件区 `#layer1TagFilterSection`,默认隐藏,通过穿透跳转设置 `currentLayer1Tag` 后显示当前标签 + 清除按钮
- 新增 db_manager 方法 `get_tag_distribution(group)` 按组统计 A/C/D 三层标签的使用频次

**F059 批量重跑 + AI 去重联动**
- 提取管理新增第 4 张卡"批量重跑"
- 候选列表 UI:文件名 + 知识点计数 + 含注解警告(橙色)+ 截断计数
- 执行流程:
  - Step 1:`operation_hook("batch_rerun")` 强制备份,失败直接终止
  - Step 2:逐文件 `delete_extracted_kps_by_source_file`(只删 pending,保留 confirmed/ignored 审核成果)
  - Step 3:逐文件走 `extract_from_file` 完整提取链(F057 截断补救 / F058 质检降级 / Step 8 去重联动)
  - Step 4:全部完成后统一跑 `scan_incremental` 跨文件 AI 去重
- 新增后端接口:
  - `GET /api/tools/batch-rerun-scan` 扫描候选文件列表
  - `POST /api/tasks/batch_rerun` 启动批量重跑任务(task type="batch_rerun")
- 含注解文件不禁用:注解的保留依赖 db 层 `delete_extracted_kps_by_source_file` 合约(只删 pending knowledge_points,不触 annotations 表)
- 进度条复用既有任务框架:`checkRunningTask` 的 titles 字典新增 `"batch_rerun":"批量重跑进行中"`

**knowledge_points 查询增强**
- `get_all_knowledge_points` 签名补齐 `qa_source_filter` 和 `layer1_tag` 参数(v2.2.3 遗留 bug)
- layer1_tag 支持 A/C/D 三组 27+ 一级标签穿透筛选

### 修复

**Step 8 增量重复检测从未触发**
- `extract_from_file` Step 8 原代码用 `info["id"]`,但 `kps_info` 实际存的是 `"kp_id"`,导致 `new_ids` 一直为空
- v2.3.0-part1 改为 `info["kp_id"]`,每次提取后增量重复检测恢复正常触发
- 该 bug 自 v2.2.0 起潜伏至今
- F059 批量重跑同步对齐

### 向下兼容

`/api/tools/duplicate-scan` 和 `/api/tools/duplicate-reset-rescan` 两个旧接口保留不变,供浏览器缓存的旧 review.html 继续调用。

### 前端改动汇总(review.html)

- Header 版本号 v2.2.3 → v2.3.0-part1
- 工具箱卡片数 10 → 9(合并两张为一张)
- 提取管理卡片数 3 → 4(新增批量重跑)
- 仪表盘卡片数 11 → 14(新增 A/C/D 标签分布三张)
- 新增 `currentLayer1Tag` 全局状态串联 dashJump / loadKnowledgePoints / showActiveFilters / clearAllFilters
- 新增函数:`updateLayer1TagFilterSection` / `clearLayer1TagFilter` / `renderTagCard` / `toggleTagCardMore` / `doDupUnified` / `_runDupUnified` / `showBatchRerunPanel` / `brToggleAll` / `doBatchRerun`
- 新增模态框:`#dupModeDlg`(三选一对话框)、`#batchRerunPanel`(批量重跑面板)

### v2.2.3 既有元素原样保留

Card 11 截断补救 / 事件日志按钮 / 规则兜底黄色高亮 / qa_source 筛选器 / qaBackfill 降级链 — 一字不改。

---

## v2.2.3 — 2026-04-12

**定位**:紧急 hotfix — 截断补救 + 质检三级降级 + 操作备份 + 质检补跑。三对话分批交付,全部完成。

### 修复

- **F057 R1 输出截断自动补救**:R1 输出 JSON 截断时不再丢失已提取内容;保留 deepseek_client 已解析的完整知识点,用最后一条 excerpt 定位切分点(三级定位:完整匹配→首 30 字→尾 30 字反向),重新提取尾段(最多 3 次降级至 500 字);按 `(title, excerpt前100字)` 去重合并
- **F058 质检三级降级链**:修复 V3 批量质检格式异常时条目直接跳过(qa_score 空置)的问题。新链路:`L0 批量 15 → L1 小批 3×2 轮 → L2 逐条 (QC_CHECK_SINGLE_PROMPT) → L3 本地规则兜底`;新增守门员机制确保每条 kp 都有 qa_score
- **v2.1.2 分批质检内层循环 bug**:原代码 `for qr in results` 实际只遍历最后一批 results,多批质检时前面批次分数未写入 DB;v2.2.3 重写 `_quality_check` 走三级降级链时天然消除
- **api_server 死代码清理**:删除 `task_reextract` 函数末尾 `return` 之后永远走不到的 `import time; time.sleep(1.5); webbrowser.open(...)`

### 新增

- **F060 关键操作强制备份**:6 个触发点(版本重提取 / 批量重跑 / 重复合并单条与批量 / 体检采纳 / 全库重扫 / 恢复)接入 `backup_manager.operation_hook(op_name)`。v2.2.3 已接入 4 处(reextract / dup_merge / dup_merge_batch / full_rescan),另 2 处(batch_rerun F059 / health_adopt F048)留给 v2.3.0 时在对应功能内接入
- **F060 备份保留策略**:每类 op_name 保留最近 5 个 + 总量 2GB 上限(每类兜底保留 1 个);备份文件名保留秒级 `backup_YYYYMMDD_HHMMSS_op_name.db`;备份失败抛 `BackupFailedError`,调用方精确捕获后终止操作
- **F061 历史质检补跑**:`POST /api/tools/qc_rerun` 扫 `qa_score IS NULL` 或 `qa_flags 含"格式异常"` 的条目,走 F058 降级链重跑;`GET /api/tools/qc_rerun/summary` 返回候选数量供前端按钮角标显示;按文件分组逐组补跑,自动加载 .md 缓存作为 source_content 供规则兜底反幻觉
- **事件日志查询**:`GET /api/events?event_type=&severity=&module=&file_id=&limit=500` 查询 `operation_events` 结构化事件日志
- **截断摘要接口**:`GET /api/tools/truncation_summary` 返回受影响文件数 / 累计截断次数 / 累计补救次数
- **qa_source 字段与筛选器**:`knowledge_points` 表新增 `qa_source` 字段(值域 `batch/small_batch/single/rule_fallback`);审核界面侧边栏加"质检来源"筛选区(4 选项);规则兜底条目整卡黄色高亮(`#FFFBEF` + 左侧橙色边框)+ "规则兜底" 小标签
- **仪表盘"截断补救"卡(Card 11)**:显示受影响文件数 + 累计截断次数 + 累计补救次数 + 待质检补跑数量;底部双按钮"截断事件"(预设筛选)和"全部事件"打开事件日志模态框
- **事件日志模态框**:880px 宽,6 列表格(时间 / 类型 / 严重度 / 模块 / 文件 ID / 详情),支持 event_type + severity 二次筛选
- **工具箱"质检补跑"按钮升级**:点击先查 summary 显示候选数量(未质检 + 格式异常分开计数),确认后走降级链;结果页显示已处理 / 候选总数 / 孤儿条目(经验速记)/ 错误列表 / 剩余待补跑
- **QC_CHECK_SINGLE_PROMPT(逐条质检)**:6 维度评分,输入单个知识点避免 V3 批量格式异常

### 变更

- `extractor.py` `_extract_single` 返回值契约:由"列表 / 'TRUNCATED'字符串"改为统一 dict `{kps, truncated, last_excerpt, raw_parsed, cost}`,调用方须 `result['kps']` 取数
- `extractor.py` `_extract_with_auto_split` 签名新增 `file_id` 参数(补救触发 `db.increment_truncation_count(file_id)` 和事件日志需要)
- `extractor.py` `_quality_check` 签名新增 `source_content` 参数(规则兜底用 `_excerpt_in_source` 做幻觉检查)
- `extractor.py` 新增类级常量 `QC_FLAG_MAP`(原内部局部变量提升,三级降级共用,F048 低分打磨也将复用)
- 旧 `/api/tools/qa-backfill` 接口保留但内部转发到 `_qc_rerun_core()`(向下兼容),字段映射保持原响应格式(`processed→checked`,`errors 数组长度 → errors 数字`)
- 仪表盘 API 响应新增字段:`truncation` / `qc_rerun` / `qa_source_distribution`
- 主页标题和 header 版本号:v2.2.2 → v2.2.3

### 数据库变更

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

### 关键决策记录

- **旧 `/api/tools/qa-backfill` 保留并转发**:hotfix 最小变更面原则;浏览器缓存的旧版 JS 不会 404;新降级链是旧批量质检的严格超集
- **工具箱"质检补跑"卡改名不新增**:老唐视角只关心功能不关心实现路径;新增第二个按钮会造成"点哪个"的决策成本
- **事件日志入口放仪表盘按钮不单独占工具箱卡位**:日志是场景溯源工具不是巡检工具,独立入口会变成死入口

---

## 早期版本精简摘要

### v2.2.2 — 2025 — 重复检测合并与批量处理

F051-F054 质量管控增强:多选合并 / 批量解决 / 跨页全选 / 自动刷新按钮计数。F039 重复检测 V3 精判补齐 client 参数,消除假阳性。

### v2.2.1 — 2025 — 重复组多选保留

重复组勾选框 + keep_ids 数组,支持保留多条有价值的知识点。

### v2.2.0 — 2025 — 专家注解 + 经验速记

F029 专家注解 5 类型(纠错 / 补充 / 情境 / 反例 / 引用)。F045 经验速记 V3 结构化入库。预处理保存 .md 缓存,提取优先读缓存。

### v2.1.2 — 2025 — 长任务管理 + 版本重提取

F046 管理后台(Tab 双视图 / 审核与系统管理)。F047 长任务 threading + 2 秒轮询进度。F044 版本重提取(PROMPT_VERSION 追踪)。

### v2.1.1 — 2025 — 政策依赖校验 + 重复检测

F028 政策依赖校验。F039 重复检测(本地粗筛 + V3 精判)。

### v2.1.0 — 2025 — 保鲜 + 三层标签体系

F021-F027 三层标签体系(A/B/C/D/E/F 六组 41 个一级标签 + 8 维度属性 + 关键词)。F028 保鲜扫描(checked_at + interval_days)。

### v2.0.0 — 2025 — 管理后台

Flask 本地 Web 管理后台。Tab 双视图 + 知识点 CRUD + 编辑历史追溯。

### v1.x — 2024 — 基础提取引擎

R1 提取 + 硅基流动 OCR + SQLite 底座。双 API 架构(DeepSeek 推理 + 硅基流动仅 OCR)。
