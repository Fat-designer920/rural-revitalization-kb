# CHANGELOG

> 乡村振兴知识库搭建助手 — 版本变更记录
>
> 格式：近 3 版完整 Added / Fixed / Changed / Migration 四段式。早期版本折叠为一行摘要，完整历史见 [GitHub Releases](https://github.com/Fat-designer920/rural-revitalization-kb/releases)。

---

## [v2.3.0-part3.8] - 2026-04-24 (hotfix)

**定位**:F062 白名单一次性清账(从 db_manager 单文件扩到 7 文件)+ 6 批量路由从裸 `except:pass` 升级到 `errors.append` 收集(E2 方案)+ 立规则 52 条首次应用清理 extractor/duplicate_checker 冗余迁移 import。E2E 扫分预期从 79.2 回到 92-95。

### Added

- 立规则第 52 条:代码审查兼做冗余清理 + 必验证外部调用方(详见 `01 §二`)
- `e2e_tester.py` 新增 `WHITELIST_COVERAGE` 常量(文件维度覆盖范围 set)
- `e2e_diagnosis_exporter.py` 第三段新增按文件维度视图(✅ 覆盖内漂移 vs ⚪ 未覆盖治理)
- `review.html` 新增 `#batchResultModal` + `showBatchResult()` 辅助函数

### Fixed / Changed

- `e2e_tester.py` DIM4 白名单 67→75 / DIM6 11→79,跨 7 文件;db_manager 漂移对齐 part3.4 真实行号
- `api_server.py` 6 批量路由(batch-confirm/ignore/delete/renew-freshness/mark-outdated/restore-to-pending)改 `errors.append({id, error})`,返回 JSON 新增 `errors` + `failed_count` 字段
- `review.html` 7 批量按钮 fetch 回调改混合策略(成功 toast/有失败弹 modal)
- `e2e_diagnosis_exporter.py` 第三段按文件分类展示;第七段版本表同步

### Removed(立规则 52 首次应用)

- `extractor.py` run_headless 内 5 迁移 import 整段删除 + main 双路径 fallback 简化,连带消失 10 条 dim6 `smell_silent_except` issue
- `duplicate_checker.py` main 内 migrate_v211_dup import 删除

**外部调用方验证**:extractor.run_headless 的 5 迁移 / main 双路径 / duplicate_checker.main 的 migrate,全部由 `api_server.py` 启动 Step 2 统一调度覆盖(立规则 52 强制验证,Phase 4 可复核)。

### Migration

无 schema / 无迁移 / 纯代码替换。

### Upgrade Path

1. 备份 → 替换 6 代码文件 → 推送 → 重启
2. 验收 6 项:① 批量操作成功时仍弹 toast(兼容); ② 故意失败弹 `#batchResultModal` 看详情; ③ deep E2E 总分 ≥92; ④ 诊断包第三段出现"白名单覆盖范围分布"表; ⑤⑥ CLI 独立跑 `extractor.py` / `duplicate_checker.py` 无 migrate 相关报错
3. 异常回滚到 part3.7

---

## [v2.3.0-part3.7] - 2026-04-24 (hotfix)

**定位**:F062 规则精度从"宁严勿漏"升级到"信噪比匹配现实"。上一版诊断包导出 207 条 issue,实测 85% 为规则前提与业务脱节的误报(`r` 变量被当 kp 对象 / 历史 Prompt key 被判 error / snippet 显示 `except` 行而非 `pass` 真实行),老唐看报告时信号淹没在噪音里。本版三条规则精度重构 + 诊断包第三段口径对齐。

### Fixed

- **Bug 1 — `smell_silent_except` / `smell_except_print_only` snippet 显示伪像**:规则匹配逻辑本身正确(严格只抓 `body == [Pass]` / `body == [Call(print)]`),但 `_add` 用 `h.lineno`(except 行),导致典型代码片段显示 `except Exception:` / `except CostLimitExceeded:`,让人以为"带类型的 except 也被误报"。修复:signature 和 snippet 锚点改用 `body[0].lineno`(pass/print 真实行)。**代价**:老 pending issue 因 signature 变化洗牌一次,老唐已确认接受
- **Bug 2 — `field_unknown` 规则 109 条 warning 里 ~95 条是误报**:根因 `_KP_LIKE_VARS = {kp,k,row,r,first}` 把 `r` 和 `row` 当成 kp 对象,但现实里 `r` 在 db_manager 是 categories 表的 row / 在 api_server 是 Flask 返回 dict / 在工具函数是 return dict。修复:(a) `_KP_LIKE_VARS` 收窄到 `{kp}`;(b) 下划线前缀字段跳过(`kp["_keywords"]` 等业务代码挂临时字段);(c) OR 兼容写法识别(`kp.get('layer1_tags') or kp.get('tags_layer1')` 两个 key 至少一个在白名单就整组不报);(d) `_KP_AS_ALIAS_WHITELIST` 扩 8 条(related_knowledge_ids / content / description / layer[123]_tags / tags_layer[123])
- **Bug 3 — `prompt_wrong_key` 对历史 Prompt 一刀切判 error**:立规则第 13 条本意是新增 Prompt 用 `system_prompt` / `user_prompt_template`,不是强制 v2.2.0 之前的历史 Prompt(DUPLICATE_JUDGE_PROMPT 用 `{"system":...,"description":...}`)改名。读历史 key 被判 error 是假阳性。修复:error → warning + 历史 key `{system,user,description}` 白名单静默
- **Bug 4 — 诊断包第三段 dim4/dim6 count 与第四段口径错配**:第三段取 `dims["dim4"]["issues"]` 的 len(白名单过滤后 raw,upsert 去重前,140 条),第四段从 `e2e_issues` 表读(upsert 后入库,109 条),导致"第三段 dim4=140 / 第四段合计 109"自相矛盾。修复:`_render_section_whitelist` 加 `issues` 参数,count 从传入的入库 issues 按 dim_code 前缀 filter,与第四段同源

### Added

- **立规则第 9 条第 5 次应验**:追加 part3.7 案例(规则的"变量名判定口径"和"Prompt key 白名单"写在记忆里不会报错,跟业务现实脱节才暴露)
- **立规则第 13 条补注**:历史 Prompt 兼容例外(新规范只约束新增 Prompt,不强制历史迁移;要迁移走单独 hotfix)
- **立规则第 38 条补注**:"宁可多告警"指**已知真问题模式不放弃检测**,不指**规则前提可以永久不跟业务同步**。判别法则:规则改动是**收紧误报** → 合规;**放弃抓某种已知错误模式** → 违规

### Changed

- `scripts/static_analyzer.py` v2.3.0-part3-alpha1 → **v2.3.0-part3.7**(+约 75 行)
- `scripts/e2e_diagnosis_exporter.py` v2.3.0-part3.6 → **v2.3.0-part3.7**(+约 20 行)
- `00 / 01 / CHANGELOG / README` 全量同步
- 立规则总数保持 51 条(无新增立规则,只对第 9/13/38 条追加补注和案例)

### Migration

无 schema 变更 / 无迁移 / 无新增路由 / 无数据转换。纯代码替换 + 项目文件同步。

### Upgrade Path

1. 替换 `scripts/static_analyzer.py` + `scripts/e2e_diagnosis_exporter.py`
2. 推送 GitHub → 重启 `启动后台.bat`
3. 验证:工具箱→端到端测试→跑一次 deep 扫描→查看最近报告→点"导出诊断包"→检查:
   - 总 issue 数从约 207 → 约 60-90 条(降噪 55-70%)
   - 典型代码片段里 `smell_silent_except` / `smell_except_print_only` 显示真实 `pass` 行或 `print(...)` 行,**不再显示 `except X:` 伪像**
   - `field_unknown` 不再报 `r.get("success")` / `row["cnt"]` / `kp["_keywords"]` 这类误报
   - `prompt_wrong_key` 不再对 duplicate_checker.py 行 392 的 `DUPLICATE_JUDGE_PROMPT["system"]` 报 error
   - 第三段白名单自检的 dim4/dim6 数字和第四段"总计 XXX 条"能相互印证(raw vs 入库不再打架)
4. **老 pending issue 洗牌警告**:signature 从 h.lineno 改到 body[0].lineno,所有 v2.3.0-part3.6 及之前的 `smell_silent_except` / `smell_except_print_only` pending issue 都会变成"孤儿态"(signature 不匹配 → 不出现在新扫描);新扫描产生的新 signature issue 是全新的 pending。老唐无需手工处理,继续按新 issue 跑正常流程即可
5. 下一版**强制回到知识生产**(v2.3.1 批量重算成熟度 + 关联体系),不再动 F062

**工程细节**:`01 立规则第 9 条第 5 次应验 + 第 13 条补注 + 第 38 条补注`

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

## 早期版本精简摘要

### v2.3.0-part3.5 — 2026-04-24 (feature)

F062 配套 —— E2E 诊断包 Markdown 导出。新模块 `scripts/e2e_diagnosis_exporter.py`(~574 行)`build_e2e_diagnosis_markdown()` 7 段输出;`api_server.py` 新增 `GET /api/tools/e2e/export/<rid>` 路由;`review.html` E2E 报告弹窗 footer 加"导出诊断包"按钮。一键打包发 Claude 做异地诊断,把 issue 审查从"网页逐条切四态"前置为"整包批量诊断"。立规则第 47/48 条(项目文件精简够用 + 工程手册只记代码里读不出的信息),倒回把工程手册从 1267 行压到 809 行(-36%)。

### v2.3.0-part3.4 — 2026-04-23 (hotfix)

质量闭环从"能跑"到"能真正指路":(a) F048 维度⑤ `get_polish_candidates` WHERE 排除集合从 `('ignored','confirmed','merged')` 收紧为 `('ignored','merged')`,允许 confirmed 条目进候选池 —— 修复全库 confirmed 化后维度⑤永久 100 分虚假绿灯;(b) F062 `_write_issues` 签名扩为 `(issues, report_id)`,`rule_id/detail` 合并进 `payload`,`_run_pipeline` 调用顺序改"save_report 拿 rid → write_issues(rid)" —— 修复报告显示 185 issue 但列表显示 0 条的幻觉数字。立规则第 9 条第 3 次应验 + 第 40 条横向边界补注 + 设计思想第 17 条"筛选边界对齐业务现状"。

### v2.3.0-part3.3 — 2026-04-23 (hotfix)

后台 UI 可信度清扫(3 处 UX 顽疾)+ E2E 白名单漂移偿债:审核统计从"裸 JSON 喷"升级为 6 段结构化卡片(overview/field_edits/type_edit_rates/prompt_versions/qa_distribution/qa_flags);保鲜扫描加 loading 弹窗;F048 维度⑤无候选时显式"已跳过打磨"提示;E2E 耗时秒级以下显示 `<1s`;E2E 白名单 35+6 条行号重扫对齐 db_manager.py v2.3.0-part3.2(实际 67+11 条 unique signature)。立规则第 46 条(前后端契约同步升级) + 设计思想第 15/16 条(前后端是两条腿 / "看起来完成" vs "用户能用")。

### v2.3.0-part3.1 — 2026-04-24 (hotfix)

两个系统性风险一次根治:(a) F061 质检补跑调旧 2 参 `_quality_check` 被 F058 扩成 5 参后崩(候选 2043 条跳过),两处调用补齐 filename + content_summary;(b) api_server 启动后追加 `db.init_tables()` 兜底(CREATE TABLE IF NOT EXISTS 幂等),解决老用户升级只替换代码不重跑 `首次安装.bat` 导致 F062 三表未建的 500 错。立规则新增 2 条:第 8 条(api_server 启动兜底 init_tables) + 第 9 条(跨版本调用外部模块前必须 grep 真实签名)。

### v2.3.0-part3 — 2026-04-24

F062 端到端健康测试 Agent 三对话拆分全闭环:api_server +422 行 7 路由 + `_e2e_readiness_check` / `_e2e_progress_adapter` 辅助函数 + review.html +770 行工具箱第 12 卡 + issue 四态切换 UI + 软提醒逻辑(>7 天淡黄 / >14 天红)。对话 1/3(part3-alpha1)基础层 + 对话 2/3(part3-alpha2)引擎层已先期落地,本版为界面层收尾。3 张 F062 表被消费,零 schema 改动。

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
