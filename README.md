# 乡村振兴知识库搭建助手

> 基于 DeepSeek R1/V3 双模型的专业知识库构建工具，面向四川乡村振兴领域。
>
> **知识工厂：原料 → 加工 → 质检 → 产品 → 卖钱。底座是知识库，上面长出多种产品形态。**
>
> **当前版本：v2.3.0-part3（F062 端到端健康测试 Agent 界面层，对话 3/3 正式版全闭环）**

---

## 系统定位

这不是一个普通的文档管理工具，而是一个**知识工厂**——将行业文件、政策法规和 20 年实战经验加工成可变现的知识产品。

**核心竞争力：** 每一条知识点都有入库质检、人工审核、政策验证、定期保鲜的完整质量链。**500 条精品级知识 > 5000 条草稿级内容**，老唐的加工（判断/注解/验证）才是付费点。

| 阶段 | 做什么 | 验证什么 |
|------|--------|---------|
| 当前 | 自用知识库做咨询，边用边喂料加注解 + **定期体检打磨** + **端到端健康扫描（v2.3.0-part3 全闭环）** | 效率提升 + 系统稳定性 |
| v2.3.2 后 | 本地问答助手自用 + 分享朋友试用 | 回答质量 / 体验 / 付费意愿 |
| 200 条精品+ | 写政策解读文章发行业圈子 | 内容付费意愿 |
| 300 条精品+ | 云端问答助手产品化 | C 端订阅 |
| 500 条精品+ | 投标辅助 / 培训 / 合规自检 | B 端高客单价 |

---

## v2.3.0-part3 本次交付内容（F062 界面层，对话 3/3 正式版）

v2.3.0-part3 是 **F062 端到端健康测试 Agent** 的三对话拆分**收官交付**。本次落地对话 3 界面层（api_server 路由 + review.html 第 11 卡 + 收尾三件套 + db_manager 对称补齐），与对话 1 基础层 + 对话 2 引擎层合流，F062 六维度扫描 + 四态 issue 跟踪 Agent 全闭环上线：

### 界面层核心交付

**`scripts/api_server.py`（v2.3.0-part2.2 → v2.3.0-part3，+422 行，2834 → 3256 行）**

- F062 端到端健康测试 Agent 的**界面后端**。新增 7 个 F062 路由（全部追加在 main() 之前，既有代码零改动）：
  - `GET /api/tools/e2e/latest` —— 最近一次扫描概要 + 软提醒徽章数据源（total_score 从 full_report_json 解出，决策 Q4 不回改 db）
  - `POST /api/tools/e2e/start` —— 启动扫描（scan_depth: quick|deep，白名单兜底 quick 不 400），走 `_task_lock` 单例 + 后台线程
  - `GET /api/tools/e2e/history?limit=20` —— 历史报告列表（走 `db.get_e2e_test_report_list`）
  - `GET /api/tools/e2e/report/<rid>` —— 单份完整报告（含 full_report_json 自动 parse）
  - `GET /api/tools/e2e/issues?status=...&dim_code=...` —— issue 四态列表（含 by_status 分组 + 维度筛选），排序 status 优先级 + last_seen_at DESC
  - `POST /api/tools/e2e/issues/<iid>/status` —— 四态切换（无限双向，决策 Q5 给老唐逃生口）
- 2 个模块级辅助函数：
  - `_e2e_readiness_check()` —— F062 启动前置 4 项自检（Prompt 双 key + static_analyzer + e2e_tester + 9 db 方法），在 `_task_lock` 之前调用
  - `_e2e_progress_adapter()` —— E2ETester 进度回调 → `_task["progress"]` 映射，9 stage 完全对齐 e2e_tester.VALID_STAGES
- 关键契约：`_task["type"]="e2e"` 前后端锁定 / scan_depth 白名单兜底 quick / `total_files=9` 固定

**`web/templates/review.html`（v2.3.0-part2 → v2.3.0-part3，+458 行，2692 → 3150 行）**

- F062 端到端健康测试 Agent 的**界面前端**。工具箱第 11 张卡 `tc-e2e`（青蓝 E 图标 #E6F3FB/#1F7AAC，决策 Q1），含软提醒徽章（绝对定位圆点，无历史灰 / ≤7 天无 / 7-14 天淡黄 / >14 天红）
- 3 个新模态框：
  - `#e2eStartDlg`（480px）：档位二选一（quick 秒级/零成本 + deep 分钟级/0.1-0.2 元）+ 历史报告按钮
  - `#e2eReportDlg`（780px）：报告详情，总分大字 + 六维度 2×3 卡（按分数阈值染色）+ 新端点清单 + 已知合理项折叠 + 查看 issue 按钮
  - `#e2eIssueDlg`（820px，**左右分栏** 决策 Q6）：左侧 160px 五 tab，右侧 issue 行（四态按钮组 + status/severity/dim_code/rule_id 徽章 + signature + 发生次数），"全部"模式按 status 分组展示（决策 Q3）
- 新增 9 个 F062 JS 函数（严格 ES5 无 emoji，Node `--check` 语法验证通过）：`_renderE2eBadge` / `doE2eStart` / `openE2eHistory` / `openE2eReport` / `renderE2eReport` / `renderE2eDimCard` / `openE2eIssues` / `_loadE2eIssues` / `_renderIssueTab` / `_renderIssueRow` / `_extractRuleFromSig` / `doE2eIssueSetStatus`
- `checkRunningTask titles` 追加 `"e2e":"端到端测试进行中"`；`showTaskProgress` + `startPolling` btns 数组追加 `"tc-e2e"`；`startPolling` 完成分支新增 e2e 弹 confirm 跳 `openE2eReport`；`init()` + `switchTab("admin")` 追加 `_renderE2eBadge()` 调用

**`scripts/db_manager.py`（v2.3.0-part3-alpha1 → v2.3.0-part3，+26 行，决策 Q7 破例补齐）**

- 新增 `get_e2e_test_report_list(limit=20)` 方法（对称 F048 `get_health_report_list`）
- 对话 1 漏项：F062 报告读写组原 3 方法，补齐后 4 方法（save + get_latest + get_detail + get_list）
- 8 方法 → 9 方法。理由：这是既有缺陷的对称补齐，不是新增功能。作为"谨慎破例"先例入档，后续严守"对话 3 不改 db"原则

### 收尾三件套

**`scripts/setup.py`**（v2.3.0-part2.2 → v2.3.0-part3）

- 核心文件校验清单追加 `scripts/static_analyzer.py`（对话 1 漏项）+ `scripts/e2e_tester.py`（对话 2 交付）

**`scripts/check_system.py`**（v2.5.1 → v2.5.2）

- [4] 数据库基础 expected 清单扩到 12 张（原 9 + F062 三张 api_endpoint_registry/e2e_test_reports/e2e_issues，决策 Q2）
- JSON 版 [4] 同扩
- 命令行版新增 [19] F062 端到端测试就绪度（4 小项：Prompt 双 key + static_analyzer 4 方法 + e2e_tester 类与便捷函数 + 9 db 方法）
- JSON 版新增 "F062 就绪度" 项

**`scripts/db_health_check.py`**（v1.1 → v1.2）

- `EXPECTED_TABLES` 追加 F062 三表
- 新增 [12/12] F062 代码层契约一致性（6 小项：E2E Prompt import+双 key + static_analyzer 4 方法 + e2e_tester 类与便捷函数 + VALID_STAGES + 9 db 方法 + 三表计数）
- main 流程追加 `check_12_f062_code_contract(conn)` 调用

### 本次设计决策（对话 3 Phase 2 锁定）

| 编号 | 决策 | 选择 |
|------|------|------|
| Q1 | tc-e2e 卡配色 | 青蓝 T 配色 #E6F3FB/#1F7AAC，图标字母 E（区分于 F048 紫色 H） |
| Q2 | check_system [4] expected 表清单 | 扩到 12 张含 F062 三表（F062 是核心业务，老库没升级该早暴露） |
| Q3 | #e2eIssueDlg 默认筛选 | 默认"全部"按 status 分组展示（老唐一打开看到全局） |
| Q4 | /latest total_score 取法 | 方案 A：不改 db，/latest 内部解 full_report_json（遵守对话 3 不改 db 纪律） |
| Q5 | issue 四态切换规则 | 无限四态切换（pending↔intermittent↔fixed↔ignored 任意方向，给老唐逃生口） |
| Q6 | #e2eIssueDlg UI 布局 | 左侧标签列 + 右侧内容区（左右分栏，浏览体验优于顶部 tab） |
| Q7 | e2e_test_reports 列表查询 | 例外允许回改 db_manager 补齐 get_e2e_test_report_list（8→9，对称 F048） |

### 老唐需要做的操作（对话 3 交付）

本次为**界面层交付 + 全闭环上线**,F062 的前后端贯通,首次可从前端真实触发扫描。操作清单:

1. **备份数据库**（启动后台的"一键备份"按钮 或 手工复制 `data/database/knowledge_base.db`）
2. **替换 6 个代码文件**：`api_server.py` / `review.html` / `db_manager.py` / `setup.py` / `check_system.py` / `db_health_check.py`
3. **推送 GitHub 后更新 Claude Projects**（5 个项目文件全量）
4. **重启服务**：关 `启动后台.bat` 再打开，浏览器强制刷新（Ctrl+F5）
5. **首次扫描**：Tab 2 → 工具箱 → 第 11 张"端到端测试"青蓝 E 卡 → 选 **quick 档**（秒级、零费用）→ 等待完成弹 confirm → 点"是"查看报告

### 验证环境自检（可选）

若想提前验证代码无语法错:
```
python -c "from scripts.db_manager import DatabaseManager; db=DatabaseManager(); print('get_e2e_test_report_list 存在:', hasattr(db, 'get_e2e_test_report_list'))"
python -c "from scripts import api_server; print('api_server 可 import')"
```

---

## v2.3.0-part3-alpha2 历史交付（F062 引擎层，对话 2/3）

### 引擎层核心交付

**`scripts/e2e_tester.py`（新建，~1250 行）**

- F062 端到端健康测试 Agent 的**引擎核心**
- 类 `E2ETester(db, client, progress_callback=None)` + 主入口 `run_full_scan(scan_depth='quick'|'deep')` + 模块级便捷函数 `run_e2e_scan(...)`
- **六维度扫描**（全部走 `_safe_dim` 单维度异常隔离，借鉴 F048）：
  - 维度① 路由自省：Flask `app.url_map` vs `api_endpoint_registry` 差集，新端点自动 register + 产 info issue
  - 维度② 启动就绪性：importlib 自检 5 核心引擎（extractor / duplicate_checker / preprocessor / experience_notes / health_checker）
  - 维度③ Prompt 调用一致性：消费对话 1 `scan_prompt_call_consistency` 结果
  - 维度④ 字段契约：消费对话 1 `scan_field_contract` 结果 + **白名单二次过滤 35 条**
  - 维度⑤ 事件语义：deep 档拉最近 7 天 warning/error 事件按 event_type 分桶抽样 30 条喂 V3 判断
  - 维度⑥ 代码异味：消费对话 1 `scan_code_smells` 结果 + **白名单二次过滤 6 条**
- **V3 调用适配器**：call_chat/chat/complete/call/generate 五方法 × messages/system_prompt 两签名（借鉴 F048）
- **白名单常量**（用真实 static_analyzer 扫描产出精确填入）：
  - `DIM4_KNOWN_FALSE_POSITIVES` 35 个 unique signature
  - `DIM6_KNOWN_FALSE_POSITIVES` 6 个 unique signature
  - `WHITELIST_REASONS` 41 条人类可读说明，前端"已知合理项"折叠展示
- **progress_callback 9 stage 锁定**：init / dim1_route / dim2_readiness / dim3_prompt / dim4_field / dim5_event / dim6_smell / done / failed
- **顶层 import 严格**：禁止 try/except 静默降级

### dry run 验证

- **quick 档**（mock db + mock client）：total_score = 87.5，6 维度全执行，dim5 标 skipped，白名单过滤 100% 命中
- **deep 档**（真实 SQLite + 3 条 warning 事件 + mock V3）：total_score = 87.84，V3 调用 3 次，成本 0.000882 元

---

## v2.3.0-part3-alpha1 历史交付（F062 基础层，对话 1/3）

### 基础层四件套

1. **`scripts/prompts/prompt_templates.py`**（v2.3.0-part2.2 → v2.3.0-part3-alpha1）
   - 新增 `E2E_RESPONSE_JUDGE_PROMPT` 正式版文本（V3 内省型 Prompt，不注入策略块）
   - 双 key 严格：`system_prompt` / `user_prompt_template`（延续 F048 对话 A 立规则）
   - 6 个占位符：endpoint / method / status_code / response_excerpt / recent_events_json / expected_behavior
   - 核心能力：识别"抢救/降级/跳过/异常继续"4 类关键词，揪出"字面 HTTP 200 但实际降级"的假绿色
   - `PROMPT_VERSION` 升到 `v2.3.0-part3-alpha1`
   - `get_all_prompt_names()` 追加 1 条 F062 登记（总 26 条）

2. **`scripts/db_manager.py`**（v2.3.0-part2.2 → v2.3.0-part3-alpha1）
   - `init_tables()` 新增 3 张 F062 表（单一来源原则，延续 v2.3.0-part2.1 立规则，零 migrate 脚本）：
     - `api_endpoint_registry`：路由登记表
     - `e2e_test_reports`：E2E 测试整体报告
     - `e2e_issues`：issue 四态跟踪（signature 去重 + occurrence_count + 偶发升级 + status CHECK 约束）
   - 索引循环新增 3 条
   - 新增 8 个方法（对话 3 破例补齐到 9 个）
   - 数据库表总数：18 → 21

3. **`scripts/static_analyzer.py`**（新建，645 行）
   - F062 维度 ③ Prompt 调用一致性 / ④ 字段契约 / ⑥ 代码异味 三个维度的纯 AST 静态规则库
   - 零 AI 调用，零 DB 写入，零第三方依赖，秒级扫描
   - 对外接口：`scan_prompt_call_consistency` / `scan_field_contract` / `scan_code_smells` + 汇总入口 `run_static_scan`
   - 规则清单 8 条

4. **`03_Prompt手册.md`** 新增"F062 E2E_RESPONSE_JUDGE_PROMPT 正式版文本"完整章节

### 设计决策（对话 1 Phase 2 已锁定）

| 决策 | 选择 |
|------|------|
| A：扫描范围 | A3 全量六维度（①路由 / ②启动 / ③Prompt AST / ④字段 AST / ⑤events V3 / ⑥代码异味 AST）|
| B：触发方式 | B1 手动触发 + 软提醒（按钮显示距上次扫描 X 天，7/14 天变色）|
| C：issue 跟踪 | C3 四态（pending / fixed / intermittent / ignored）+ 偶发升级 |
| D：深度档位 | D2 两档（quick 仅静态秒级 / deep += V3 最近 7 天事件分钟级）|

---

## 历史版本功能累积

### v2.3.0-part2.2 hotfix（F048 防护层）
- 四类系统性 bug 修复：Prompt 未落地 / import 静默降级 / 字段读取 / Prompt key 错配
- 启动就绪性自检防护墙：`_health_readiness_check()` 在 `_task_lock` 之前做 4 项自检，依赖不全时秒回 400 + details 故障清单，不污染 `_task` 单例
- `db_manager` 三个扫描查询追加 LEFT JOIN categories → `c.level1_name AS category` + `c.level2_name AS subcategory`

### v2.3.0-part2（F048 知识库体检 Agent 正式版）
- 工具箱第 10 张紫色"知识库体检"卡 + 档位选择（30/50/100/200/不限）
- 六维度扫描：健康度 / 结构分布 / 加工深度 / 关联密度 / 低分打磨 / 变现匹配度（权重 25/10/20/10/20/15）
- 三层打磨降级链：L1 主链（V3 诊断 → R1 创造打磨 → V3 校验）→ L2 保守打磨 → L3 人工兜底
- 采纳原子三步：operation_hook("health_adopt") 强制备份 → update_knowledge_point 字段智能映射 → apply_polish_suggestion 标记 applied
- 逐条 Review UI：左右对比 + 诊断折叠 + tier 三色徽章 + 按 suggestion_type 动态按钮矩阵

### v2.3.0-part2.1 hotfix
- `db_manager.init_tables()` 吸收 F048 两表 3 索引，migrate 脚本退役删除（schema 单一来源原则）

### v2.3.0-part1（工具箱整体优化）
- F049 仪表盘 + 工具箱：新增 Card 12/13/14 三组标签分布卡 + 合并"智能重复检测"三选一弹窗
- F059 批量重跑：支持文件勾选 + 含注解警告 + 自动备份 + 跨文件 AI 去重联动
- 侧边栏一级标签筛选 + Step 8 bug 修正

### v2.2.3 hotfix
- F057 R1 截断自动补救：保留已解析部分 + 末条 excerpt 定位 + 重提尾段（最多 3 次降级至 500 字）
- F058 质检三级降级链：L0 批量 15 → L1 小批 3×2 → L2 逐条 → L3 本地规则兜底
- F060 关键操作强制备份 + F061 历史质检补跑
- operation_events 表 + 事件日志 UI

---

## 商业化场景

| 场景 | 客户群 | 产品形态 |
|------|--------|---------|
| 政策解读订阅 | 乡镇干部 / 小型咨询公司 | 新政策解读 + 操作建议 + 月报 |
| 问答助手订阅 | 基层干部 / 施工项目经理 | 微信小程序 / 网页问答 |
| 行业培训课程 | 县级自然资源局 / 咨询公司 | 线下培训 + 线上课件 |
| 投标方案辅助 | 工程咨询公司 / 规划设计院 | 投标素材包自动生成 |
| 合规自检工具 | 施工企业 / 项目经理 | 在线自检 + 整改建议 |
| 数据查询与测算 | 工程咨询 / 规划设计 | 指标数据查询 + 费用测算 |

---

## 模块状态

| 模块 | 定位 | 状态 |
|------|------|------|
| 1 知识提取引擎 | 文件 → 结构化知识点（含举一反三 + 截断补救 + 重复检测 + 批量重跑） | ✅ **v2.3.0-part1 完成** |
| 2 知识审核与管理 | 审核 / 标签 / 保鲜 / 政策 / 质控（三级降级） / 管理后台 / 标签分布视图 | ✅ **v2.3.0-part1 完成** |
| 3 经验录入 | 专家注解 + 经验速记 | ✅ v2.2.0 完成 |
| 4 质量体检 | AI 全盘扫描 + 低分打磨 + 喂料建议 | ✅ **v2.3.0-part2 正式版 + v2.3.0-part2.2 hotfix** |
| 5 端到端测试 | 路由自省 + 启动就绪性 + AST 静态 + V3 语义 + 四态跟踪 | ✅ **v2.3.0-part3 全闭环（基础层 + 引擎层 + 界面层 3 对话交付）** |
| 6 本地问答助手 | 顾问式答疑 + 朋友试用 | 🚧 v2.3.2 规划中 |
| 7 内容生产引擎 | AI 辅助生成政策解读 / 指南 / 课件 | 未开发（v2.4.0+） |
| 8 云端问答产品 | 高并发问答服务 | 未开发（v3.x） |
| 9 内容分发与付费 | 产品化 + 收费 | 未开发（v3.x） |
| 10 信息采集 | 政策更新抓取 | 未开发（远期） |

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 运行环境 | Windows + Python 3.8+（便携版，绿色免安装） |
| AI 引擎 | DeepSeek API（R1 提取 + 低分打磨；V3 辅助判断 + 校验 + **E2E 响应语义判断**） |
| OCR 引擎 | 硅基流动 API（Qwen2.5-VL-72B 视觉模型） |
| 数据库 | SQLite（21 张表，v2.3.0-part3-alpha1 起新增 api_endpoint_registry / e2e_test_reports / e2e_issues） |
| Web 界面 | Flask 本地管理后台（ES5 前端，无 emoji） |
| PDF 渲染 | pymupdf |
| 操作方式 | 管理后台为主，bat 入口辅助 |

---

## 双 API 架构

| API | 用途 | 模型 | 费用 |
|-----|------|------|------|
| DeepSeek | 知识提取(R1)、低分打磨创造(R1)、分类 / 质检 / 预分析 / 政策扫描 / 重复判断 / 经验速记结构化 / 体检分析 / 打磨校验 / 问答生成 / **E2E 响应语义判断**(V3) | deepseek-reasoner / deepseek-chat | R1 约 4 元/百万 token，V3 约 1 元/百万 token |
| 硅基流动 | 扫描件 PDF 和图片的 OCR 识别（仅 OCR，不做推理） | Qwen/Qwen2.5-VL-72B-Instruct | 约 4 元/百万 token |

---

## 快速开始

### 1. 首次部署

```
双击 首次安装.bat
```

按提示完成 Python 环境检查、依赖安装、双 API Key 配置、数据库初始化。

### 2. 日常使用

```
1. 将文件放入 data/pending/ 目录
2. 双击 启动后台.bat → 自动打开管理后台
3. Tab 2 系统管理 → 提取管理
4. Tab 1 知识审核 → 人工审核
5. Tab 2 系统管理 → 工具箱 → 定期体检打磨 / 端到端健康扫描（v2.3.0-part3 ✅ 全闭环）
```

### 3. 维护工具（Tab 2 工具箱）

系统检查 / 一键备份 / 恢复备份 / 保鲜扫描 / 智能重复检测 / 政策补跑 / 质检补跑 / 审核统计 / API 费用 / **知识库体检（v2.3.0-part2 ✅）** / **端到端健康测试（v2.3.0-part3 ✅ 全闭环）**

---

## 目录结构

```
rural-revitalization-kb/
├── scripts/                # Python 脚本
│   ├── prompts/            # Prompt 模板（26 个，v2.3.0-part3-alpha1 新增 E2E_RESPONSE_JUDGE_PROMPT）
│   ├── api_server.py       # 管理后台 API（v2.3.0-part3，+F062 界面层 7 路由）
│   ├── extractor.py        # 知识提取引擎（含 F057/F058 + Step 8 修正）
│   ├── deepseek_client.py  # API 封装（DeepSeek + 硅基流动）
│   ├── preprocessor.py     # 文件预处理 + .md 缓存
│   ├── db_manager.py       # 数据库管理（v2.3.0-part3，F062 9 方法）
│   ├── experience_notes.py # 经验速记模块
│   ├── config_wizard.py    # 配置向导（双 API Key）
│   ├── check_system.py     # 系统检查（v2.5.2，+F062 就绪度）
│   ├── duplicate_checker.py# 重复检测
│   ├── policy_validator.py # 政策依赖校验
│   ├── freshness_checker.py# 保鲜扫描
│   ├── backup_manager.py   # 备份恢复 + operation_hook 钩子（6 触发点）
│   ├── review_analytics.py # 审核统计
│   ├── tag_config.py       # 标签体系配置
│   ├── file_reader.py      # 多格式文件读取
│   ├── setup.py            # 初始化（v2.3.0-part3）
│   ├── upgrade_manager.py  # 架构升级迁移
│   ├── health_checker.py   # F048 知识库体检引擎（v2.3.0-part2.2，~1360 行）
│   ├── static_analyzer.py  # F062 静态分析模块（v2.3.0-part3-alpha1 新建，645 行，维度③④⑥ AST 规则库）
│   ├── e2e_tester.py       # F062 端到端测试引擎（v2.3.0-part3-alpha2 新建，~1250 行，六维度扫描 + V3 判断 + 白名单过滤）
│   └── db_health_check.py  # 数据层只读体检脚本（v1.2，+F062 代码层契约）
├── web/templates/          # 前端页面
│   └── review.html         # 管理后台（v2.3.0-part3，工具箱 11 卡）
├── data/                   # 数据目录
├── backups/                # 备份目录
├── config/                 # 配置文件
├── 启动后台.bat
├── 首次安装.bat
├── CHANGELOG.md
└── README.md
```

---

## 知识体系

### 分类体系（5 大类 27+ 子类）

1. **政策库**（法规依据）
2. **案例库**（项目参考）
3. **经验库**（差异化资产）
4. **工具库**（可复用模板）
5. **数据库**（数据支撑）

### 三层标签体系

- **第一层 分类标签**：6 组 41 个（业务领域 / 项目阶段 / 知识形态 / 客户视角 / 稀缺度 / 内容状态）
- **第二层 属性标签**：8 个维度
- **第三层 关键词**：AI 自由提取 5-15 个

---

## 迭代路线

| 版本 | 定位 | 状态 |
|------|------|------|
| v1.0 ~ v2.2.2 | 基础 → 提取 → 管理 → 资产沉淀 → 质量管控 | ✅ 已完成 |
| v2.2.3 hotfix | 紧急 bug 修复 + 护栏 | ✅ 已完成 |
| v2.3.0-part1 | 工具箱整体优化 | ✅ 已完成 |
| v2.3.0-part2 | F048 知识库体检 Agent | ✅ 已完成 |
| v2.3.0-part2.1 | schema 整合 hotfix | ✅ 已完成 |
| v2.3.0-part2.2 | F048 防护层 hotfix（四类系统性 bug） | ✅ 已完成 |
| v2.3.0-part3-alpha1 | F062 基础层（对话 1/3） | ✅ 已交付（2026-04-23） |
| v2.3.0-part3-alpha2 | F062 引擎层（对话 2/3） | ✅ 已交付（2026-04-23） |
| **v2.3.0-part3** | **F062 界面层正式版（对话 3/3 全闭环）** | ✅ **本次交付（2026-04-24）** |
| v2.3.1 | 批量重算成熟度 + 关联体系 | 规划中 |
| v2.3.2 | 本地问答助手 | 规划中 |
| v2.4.0+ | 按需再议 | 远期 |
| v3.x | 产品化 | 远期 |

---

## 协作流程

### 五阶段迭代工作流

1. **需求提交** → 老唐描述问题
2. **影响范围评估** → Claude 给修改逻辑 + 决策建议
3. **代码交付** → 完整文件 + 项目文件全量更新 + 操作清单
4. **用户执行** → 备份 → 替换 → 推送 → 更新 Projects → 验证
5. **回滚** → 有问题新开对话

### 技术文档（Claude Projects 4 个项目文件）

- `00_项目全景.md`：模块状态 / 迭代路线 / 商业化路径
- `01_工程手册.md`：代码文件清单 / 技术踩坑 / 关键设计决策
- `02_知识体系.md`：五大类分类 + 三层标签
- `03_Prompt手册.md`：26 个 Prompt 模板清单（含 F048 6 个 + F062 1 个）

### GitHub 仓库

https://github.com/Fat-designer920/rural-revitalization-kb

---

## 关键约束（改代码时必读）

- **bat 文件**：GBK 编码 + CRLF 换行
- **review.html**：零 emoji + 严格 ES5（无箭头函数、无 const/let、无 async/await、无模板字符串）
- **api_server.py**：`Response(html, mimetype="text/html; charset=utf-8")` 返回 HTML
- **R1 调用**：不传 temperature，不传图片，超时 300 秒，分段 ≤ 3000 字
- **OCR**：用硅基流动不用 DeepSeek
- **数据库**：所有删除必须手动级联 annotations
- **v2.2.3 铁律 1**：每条知识点必须有 qa_score + qa_source，禁止"跳过"灰色地带
- **v2.2.3 铁律 2**：6 个关键操作触发点必须先 `operation_hook(op_name)` 备份
- **v2.3.0-part2.1 立规则**：schema 单一来源，`init_tables()` 是唯一建表真相；migrate 脚本升完立即退役
- **v2.3.0-part2.2 立规则 1**：禁止"包级静默降级"（try/except + None 兜底）
- **v2.3.0-part2.2 立规则 2**：文档契约字段名必须从 schema 源文件取真相
- **v2.3.0-part2.2 立规则 3**：长任务启动就绪性自检必须在 `_task_lock` 之前
- **v2.3.0-part2.2 立规则 4**：项目文件契约与代码实装对齐窗口（alpha 骨架 → beta 锚点 → 正式版 metrics）
- **v2.3.0-part3-alpha1 立规则 1**：F062 severity 严格对齐 operation_events CHECK，用 `info`/`warning`/`error`，禁 `warn` 简写
- **v2.3.0-part3-alpha1 立规则 2**：F062 e2e_issues.status 四态 CHECK 强约束（pending/fixed/intermittent/ignored），Python 层 + SQL 层双重兜底
- **v2.3.0-part3-alpha1 立规则 3**：偶发升级阈值为类级常量（E2E_INTERMITTENT_WINDOW_DAYS=7 / E2E_INTERMITTENT_UPGRADE_THRESHOLD=5）
- **v2.3.0-part3-alpha1 立规则 4**：static_analyzer 保持"宁可多告警"的敏锐度，"已知合理项"由引擎层白名单二次过滤，不允许反向放宽静态规则
- **v2.3.0-part3 立规则 1**：`_task["type"]="e2e"` 前后端口径字面锁定（api_server + review.html `checkRunningTask.titles["e2e"]`）；避免 F048 `health_check` vs `health` 口径走样教训
- **v2.3.0-part3 立规则 2**：`progress_adapter` 的 `_E2E_STAGE_MAP` 必须完全覆盖 e2e_tester `VALID_STAGES`（当前 9 种），`total_files` 跟随 VALID_STAGES 基数；未来 e2e_tester 加 stage 同步改 adapter
- **v2.3.0-part3 立规则 3**：`/latest` 接口 `total_score` 走 `full_report_json` 解析（决策 Q4），不回改 db 顶层列；下一小版本再统一整理 db 列体系
- **v2.3.0-part3 立规则 4**：issue 四态切换允许无限双向（决策 Q5）；给老唐逃生口，不强制单向关闭

---

## 变更日志

详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 许可证与支持

本项目为个人实战资产沉淀工具，当前阶段仅供老唐本人使用。未来商业化路径见 `00_项目全景.md`。

## v2.3.0-part3 致谢

感谢老唐在界面层 3 轮对话里反复坚持"把方案讲到老唐能懂为止再动代码"的规矩。Phase 2 的 7 个决策（Q1-Q7）每一个都有利弊分析、有反驳（Q4 方案 A vs B）、有破例理由（Q7 谨慎破例），这是项目从"代码跑通"升级为"架构能自洽"的关键抓手。F062 三对话拆分也证明了工程纪律：基础层定契约 → 引擎层消费契约 → 界面层只接引擎，每一层交付前的 dry run + 项目文件对齐，让最终集成一次过，没有返工。

## v2.3.0-part3-alpha2 致谢

感谢老唐在对话 1 交付的基础上提供完整真实的 db_manager.py v2.3.0-part3-alpha1 源文件，让 Claude 本地跑一次 static_analyzer 就拿到 35+6 条精确 unique signature，白名单不再预估不再占位。这种"数据真相源头化"的协作模式，让对话 2 的交付从一开始就是可验证的，而不是"代码写完再跑集成测试看行不行"。

对话 1 → 对话 2 的契约 100% 兑现：8 个 db 方法 + 1 个 Prompt 双 key 结构 + static_analyzer 四 key 返回结构，全部在引擎层顶层 import 消费，零修改基础层。这就是"基础层先立契约，引擎层只做消费"的工程化兑现。

## v2.3.0-part3-alpha1 致谢

感谢老唐的 F048 线上实测挖出了 4 类系统性 bug。这些 bug 的教训直接转化为 F062 的维度③⑥规则库 —— 未来再有新代码踩同样的坑，static_analyzer 能在扫描时秒级抓出来，不再等"假绿色生产事故"之后才复盘。这就是"发现一个问题，解决一类问题"原则的工程化兑现。
