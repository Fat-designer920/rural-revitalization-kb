# 乡村振兴知识库搭建助手

> 基于 DeepSeek R1/V3 双模型的专业知识库构建工具，面向四川乡村振兴领域。
>
> **知识工厂：原料 → 加工 → 质检 → 产品 → 卖钱。底座是知识库，上面长出多种产品形态。**
>
> **当前版本：v2.3.0-part3-alpha2（F062 端到端健康测试 Agent 引擎层，对话 2/3 已交付；对话 3 界面层待开发）**

---

## 系统定位

这不是一个普通的文档管理工具，而是一个**知识工厂**——将行业文件、政策法规和 20 年实战经验加工成可变现的知识产品。

**核心竞争力：** 每一条知识点都有入库质检、人工审核、政策验证、定期保鲜的完整质量链。**500 条精品级知识 > 5000 条草稿级内容**，老唐的加工（判断/注解/验证）才是付费点。

| 阶段 | 做什么 | 验证什么 |
|------|--------|---------|
| 当前 | 自用知识库做咨询，边用边喂料加注解 + **定期体检打磨** + **端到端健康扫描（v2.3.0-part3 进行中）** | 效率提升 + 系统稳定性 |
| v2.3.2 后 | 本地问答助手自用 + 分享朋友试用 | 回答质量 / 体验 / 付费意愿 |
| 200 条精品+ | 写政策解读文章发行业圈子 | 内容付费意愿 |
| 300 条精品+ | 云端问答助手产品化 | C 端订阅 |
| 500 条精品+ | 投标辅助 / 培训 / 合规自检 | B 端高客单价 |

---

## v2.3.0-part3-alpha2 本次交付内容（F062 引擎层，对话 2/3）

v2.3.0-part3 是 **F062 端到端健康测试 Agent** 的三对话拆分开发。本次交付对话 2 引擎层,消费对话 1 基础层契约,为对话 3 界面层铺垫:

### 引擎层核心交付

**`scripts/e2e_tester.py`（新建,~1250 行）**

- F062 端到端健康测试 Agent 的**引擎核心**
- 类 `E2ETester(db, client, progress_callback=None)` + 主入口 `run_full_scan(scan_depth='quick'|'deep')` + 模块级便捷函数 `run_e2e_scan(...)`
- **六维度扫描**(全部走 `_safe_dim` 单维度异常隔离,借鉴 F048):
  - 维度①路由自省:Flask `app.url_map` vs `api_endpoint_registry` 差集,新端点自动 register + 产 info issue
  - 维度②启动就绪性:importlib 自检 5 核心引擎(extractor / duplicate_checker / preprocessor / experience_notes / health_checker)
  - 维度③Prompt 调用一致性:消费对话 1 `scan_prompt_call_consistency` 结果
  - 维度④字段契约:消费对话 1 `scan_field_contract` 结果 + **白名单二次过滤 35 条**
  - 维度⑤事件语义:deep 档拉最近 7 天 warning/error 事件按 event_type 分桶抽样 30 条喂 V3 判断
  - 维度⑥代码异味:消费对话 1 `scan_code_smells` 结果 + **白名单二次过滤 6 条**
- **V3 调用适配器**:call_chat/chat/complete/call/generate 五方法 × messages/system_prompt 两签名(借鉴 F048)
- **白名单常量**(用真实 static_analyzer 扫描产出精确填入):
  - `DIM4_KNOWN_FALSE_POSITIVES` 35 个 unique signature(SQL 别名 9 / 其他表字段 8 / F062 新表字段 11 / JOIN-GROUP BY 结果 7)
  - `DIM6_KNOWN_FALSE_POSITIVES` 6 个 unique signature(全是合理 silent_except 兜底)
  - `WHITELIST_REASONS` 41 条人类可读说明,对话 3 前端"已知合理项"折叠展示
- **progress_callback 9 stage 锁定**:init / dim1_route / dim2_readiness / dim3_prompt / dim4_field / dim5_event / dim6_smell / done / failed
- **顶层 import 严格**:禁止 try/except 静默降级,缺失依赖直接 ImportError 崩

### 对话 2 开发纪律兑现

| 关卡项 | 状态 |
|------|------|
| 顶层 import `E2E_RESPONSE_JUDGE_PROMPT` + `PROMPT_VERSION` + `static_analyzer` | ✅ |
| Prompt key 严格 `system_prompt`/`user_prompt_template` | ✅ |
| 字段读法严格(零 `kp['id']` / `source_authority` / `access_level` 错误) | ✅ |
| severity 严格三态(`warn` 自动转 `warning`) | ✅ |
| issue 四态走 db.upsert_e2e_issue(CHECK 兜底) | ✅ |
| 单维度异常隔离 `_safe_dim` 包装全部六维度 | ✅ |
| 白名单二次过滤不反向改弱 static_analyzer | ✅ |
| **不碰** api_server / review.html / setup / check_system / db_manager / prompt_templates / static_analyzer | ✅ |
| static_analyzer 自扫 e2e_tester.py:dim3=0 / dim4=2 自身合理 / dim6=4 自身合理 | ✅ |

### dry run 验证

- **quick 档**(mock db + mock client):total_score = 87.5,6 维度全执行,dim5 标 skipped,白名单过滤 100% 命中
- **deep 档**(真实 SQLite + 3 条 warning 事件 + mock V3):total_score = 87.84,V3 调用 3 次,成本 0.000882 元,dim5 采样判断完整

### 老唐需要做的操作(对话 2 交付)

⚠️ 本次为**引擎层交付**,对话 3 界面层还未落地,**请勿在本机跑端到端扫描**(缺 api_server 路由入口,无法从前端触发)。本次只需要:

1. **不升级本地数据库**:对话 1 已落地的 3 张新表在对话 2 引擎层被 `upsert_e2e_issue` / `save_e2e_test_report` 消费,但触发点是对话 3 的 `/api/tools/e2e/start` 路由。本机 setup.py 升级时机仍在对话 3 交付后
2. **替换 1 个代码文件 + 5 个项目文件到 GitHub**:
   - `scripts/e2e_tester.py`(新建,~1250 行)
   - `00_项目全景.md` / `01_工程手册.md` / `03_Prompt手册.md` / `CHANGELOG.md` / `README.md`(增量更新)
3. **推送 GitHub 后更新 Claude Projects**(5 个项目文件全量)
4. **等待对话 3 界面层交付后,一次性完成首次端到端测试联调**(届时升级数据库)

### 验证环境自检(可选)

若想提前验证引擎层代码无语法错:
```
python -c "from scripts.e2e_tester import E2ETester, run_e2e_scan, DIM4_KNOWN_FALSE_POSITIVES, DIM6_KNOWN_FALSE_POSITIVES; print('OK:', len(DIM4_KNOWN_FALSE_POSITIVES), '+', len(DIM6_KNOWN_FALSE_POSITIVES))"
```
预期输出:`OK: 35 + 6`

---

## v2.3.0-part3-alpha1 历史交付(F062 基础层,对话 1/3)

v2.3.0-part3 是 **F062 端到端健康测试 Agent** 的三对话拆分开发。本次交付对话 1 基础层，为对话 2 引擎层和对话 3 界面层铺垫：

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
     - `api_endpoint_registry`：路由登记表（endpoint PK + methods + first_seen_at + last_tested_at + test_template_json）
     - `e2e_test_reports`：E2E 测试整体报告（trigger_type + scan_depth + 六维汇总 + new_endpoints_json + full_report_json）
     - `e2e_issues`：issue 四态跟踪（signature 去重 + occurrence_count + 偶发升级 + status CHECK 约束）
   - 索引循环新增 3 条：`idx_e2e_report_created` / `idx_e2e_issue_status` / `idx_e2e_issue_signature`
   - 新增 8 个方法：路由自省 3 + 报告读写 3 + issue 四态 2
   - 数据库表总数：18 → 21

3. **`scripts/static_analyzer.py`**（新建，645 行）
   - F062 维度 ③ Prompt 调用一致性 / ④ 字段契约 / ⑥ 代码异味三个维度的纯 AST 静态规则库
   - 零 AI 调用，零 DB 写入，零第三方依赖，秒级扫描
   - 对外接口：`scan_prompt_call_consistency` / `scan_field_contract` / `scan_code_smells` + 汇总入口 `run_static_scan`
   - 规则清单 8 条（rule_id）：
     - 维度③：`smell_prompt_try_import` / `smell_prompt_except_none` / `prompt_wrong_key` / `smell_dead_none_guard`
     - 维度④：`field_unknown`
     - 维度⑥：`smell_try_except_none_import` / `smell_silent_except` / `smell_except_print_only`

4. **`03_Prompt手册.md`**
   - 新增"F062 E2E_RESPONSE_JUDGE_PROMPT 正式版文本"完整章节
   - 调用位置对照表追加 E2E_RESPONSE_JUDGE_PROMPT 一行
   - 策略块注入表补充 F062 列

### 设计决策（对话 1 Phase 2 已锁定）

| 决策 | 选择 |
|------|------|
| A：扫描范围 | A3 全量六维度（① 路由自省 / ② 启动就绪性 / ③ Prompt 调用一致性 / ④ 字段契约 / ⑤ operation_events V3 语义 / ⑥ 代码异味）；③④⑥ 纯 AST 零 AI 成本 |
| B：触发方式 | B1 手动触发 + 软提醒（按钮显示距上次扫描 X 天，7/14 天变色，对话 3 前端落地）|
| C：issue 跟踪 | C3 四态（pending / fixed / intermittent / ignored）+ 偶发升级（一周 > 5 次 intermittent → pending）|
| D：深度档位 | D2 两档（quick 仅静态秒级 / deep += V3 最近 7 天事件分钟级）|

### 对话 1 验证清单

- [x] 21 张表 + 24 条索引 用全新 sqlite 库 `init_tables()` 一次建成（实测通过）
- [x] 8 个新方法 smoke test 全通过（register_endpoint UPSERT / upsert_e2e_issue 合并与回归 / set_e2e_issue_status 四态切换 / 偶发升级阈值触发）
- [x] `from scripts.prompts.prompt_templates import E2E_RESPONSE_JUDGE_PROMPT` 顶层 import 成功；双 key 齐全；6 个占位符完整
- [x] `static_analyzer` 扫 mock 含 4 类 bug 模式的文件，全部规则精确命中（try/except Prompt / 错误 key / None 死防御 / except pass）
- [x] 运行 `python -m py_compile` 对三个代码文件编译通过
- [x] severity / status CHECK 约束生效：传 "warn"（旧口径）/ "bad_state" 等非法值立即失败

### 老唐需要做的操作（对话 1 交付）

⚠️ 本次为**基础层交付**，对话 2 引擎层和对话 3 界面层还未落地，**请勿在本机升级数据库结构**。本次只需要：

1. **不升级本地数据库**：对话 1 的 3 张新表只有在对话 2/3 调用时才需要实体生效。若现在就跑 `setup.py`，老数据库会多出 3 张空表但无功能，没有实际意义
2. **替换 3 个代码文件到 GitHub**（见操作清单）
3. **推送 GitHub 后更新 Claude Projects**（5 个项目文件全量）
4. **等待对话 2 引擎层交付后，一次性完成首次端到端测试验证**（届时升级数据库）

### 验证环境自检（可选）

若想提前验证基础层代码无语法错：
```
python -c "from scripts.prompts.prompt_templates import E2E_RESPONSE_JUDGE_PROMPT; print('OK:', list(E2E_RESPONSE_JUDGE_PROMPT.keys()))"
python -c "import scripts.static_analyzer as sa; print('OK:', sa.__doc__[:60])"
```

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
| 5 端到端测试 | 路由自省 + 启动就绪性 + AST 静态 + V3 语义 + 四态跟踪 | 🚧 **v2.3.0 Part3 进行中（对话 1/2 ✅,对话 3 待开发）** |
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
5. Tab 2 系统管理 → 工具箱 → 定期体检打磨 / 端到端健康扫描（v2.3.0-part3 进行中）
```

### 3. 维护工具（Tab 2 工具箱）

系统检查 / 一键备份 / 恢复备份 / 保鲜扫描 / 智能重复检测 / 政策补跑 / 质检补跑 / 审核统计 / API 费用 / **知识库体检（v2.3.0-part2 ✅）** / **端到端健康测试（v2.3.0 Part3 规划，对话 3 前端落地）**

---

## 目录结构

```
rural-revitalization-kb/
├── scripts/                # Python 脚本
│   ├── prompts/            # Prompt 模板（26 个，v2.3.0-part3-alpha1 新增 E2E_RESPONSE_JUDGE_PROMPT）
│   ├── api_server.py       # 管理后台 API（v2.3.0-part2.2）
│   ├── extractor.py        # 知识提取引擎（含 F057/F058 + Step 8 修正）
│   ├── deepseek_client.py  # API 封装（DeepSeek + 硅基流动）
│   ├── preprocessor.py     # 文件预处理 + .md 缓存
│   ├── db_manager.py       # 数据库管理（v2.3.0-part3-alpha1，新增 F062 3 表 + 8 方法）
│   ├── experience_notes.py # 经验速记模块
│   ├── config_wizard.py    # 配置向导（双 API Key）
│   ├── check_system.py     # 系统检查 v2.5
│   ├── duplicate_checker.py# 重复检测
│   ├── policy_validator.py # 政策依赖校验
│   ├── freshness_checker.py# 保鲜扫描
│   ├── backup_manager.py   # 备份恢复 + operation_hook 钩子（6 触发点）
│   ├── review_analytics.py # 审核统计
│   ├── tag_config.py       # 标签体系配置
│   ├── file_reader.py      # 多格式文件读取
│   ├── setup.py            # 初始化
│   ├── upgrade_manager.py  # 架构升级迁移
│   ├── health_checker.py   # F048 知识库体检引擎（v2.3.0-part2.2，~1360 行）
│   ├── static_analyzer.py  # F062 静态分析模块（v2.3.0-part3-alpha1 新建，645 行，维度③④⑥ AST 规则库）
│   ├── e2e_tester.py       # F062 端到端测试引擎（v2.3.0-part3-alpha2 新建，~1250 行，六维度扫描 + V3 判断 + 白名单过滤）
│   └── db_health_check.py  # 数据层只读体检脚本
├── web/templates/          # 前端页面
│   └── review.html         # 管理后台
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
| **v2.3.0-part3-alpha2** | **F062 引擎层（对话 2/3）** | ✅ **本次交付** |
| v2.3.0-part3 | F062 界面层正式版（对话 3/3） | 待开发 |
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
- `03_Prompt手册.md`：26 个 Prompt 模板清单（含 F048 6 个 + F062 1 个,v2.3.0-part3-alpha2 仅消费对话 1 已落地的 E2E_RESPONSE_JUDGE_PROMPT,不新增 Prompt）

### GitHub 仓库

https://github.com/Fat-designer920/rural-revitalization-kb

---

## 关键约束（改代码时必读）

- **bat 文件**：GBK 编码 + CRLF 换行
- **review.html**：零 emoji + 严格 ES5
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
- **v2.3.0-part3-alpha1 立规则 3**：偶发升级阈值为类级常量（E2E_INTERMITTENT_WINDOW_DAYS=7 / E2E_INTERMITTENT_UPGRADE_THRESHOLD=5），方便对话 2 按需覆盖
- **v2.3.0-part3-alpha1 立规则 4**：static_analyzer 保持"宁可多告警"的敏锐度，"已知合理项"由对话 2 引擎层白名单二次过滤，不允许反向放宽静态规则

---

## 变更日志

详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 许可证与支持

本项目为个人实战资产沉淀工具，当前阶段仅供老唐本人使用。未来商业化路径见 `00_项目全景.md`。

## v2.3.0-part3-alpha2 致谢

感谢老唐在对话 1 交付的基础上提供完整真实的 db_manager.py v2.3.0-part3-alpha1 源文件,让 Claude 本地跑一次 static_analyzer 就拿到 35+6 条精确 unique signature,白名单不再预估不再占位。这种"数据真相源头化"的协作模式,让对话 2 的交付从一开始就是可验证的,而不是"代码写完再跑集成测试看行不行"。

对话 1 → 对话 2 的契约 100% 兑现:8 个 db 方法 + 1 个 Prompt 双 key 结构 + static_analyzer 四 key 返回结构,全部在引擎层顶层 import 消费,零修改基础层。这就是"基础层先立契约,引擎层只做消费"的工程化兑现。

## v2.3.0-part3-alpha1 致谢

感谢老唐的 F048 线上实测挖出了 4 类系统性 bug。这些 bug 的教训直接转化为 F062 的维度③⑥规则库 —— 未来再有新代码踩同样的坑，static_analyzer 能在扫描时秒级抓出来，不再等"假绿色生产事故"之后才复盘。这就是"发现一个问题，解决一类问题"原则的工程化兑现。
