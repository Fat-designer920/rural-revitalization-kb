# CHANGELOG

> 乡村振兴知识库搭建助手 — 版本变更记录
>
> 格式:近 3 版完整 Added / Fixed / Changed / Migration 四段式;早期版本折叠为单段摘要(每版 ≤ 5 行)。立规则与架构契约统一沉淀在 `01_工程手册.md`,本文件不重复。完整历史见 [GitHub Releases](https://github.com/Fat-designer920/rural-revitalization-kb/releases)。

---

## [v2.3.4-hotfix3] - 2026-04-28 (hotfix - 思考型模型识别 + JSON Lines 解析降级兼容)

**定位**:v2.3.4-hotfix1 上线第二天老唐喂料实测翻车,救援链全部 timeout + 0 条 kp 误判为 L0 失败 + R1 输出 0.099 元全丢,**3 个独立 BUG 一次根治**。本版与 v2.3.5-part1 正交(知识关系网络不动),只修提取链。

诊断 3 个独立 BUG:
1. **BUG#1 timeout 漏判**(deepseek_client.py 第 53 行):`R1_MODELS = {"deepseek-reasoner"}` 集合只认 DeepSeek 官方一个名字,hotfix1 引入的硅基思考型模型(`Pro/deepseek-ai/DeepSeek-R1` / `Pro/moonshotai/Kimi-K2.6`)走 `_is_r1` 判定 False → timeout=120s(短)而非 300s → 思考型 reasoning_content 输出 200+ 秒**必然超时** → L1/L2 救援链全军覆没
2. **BUG#2A 0 条 kp 误判**(extractor.py 第 340 行):`if not result["truncated"] and kps: return kps` 致命 `and kps`,导致 R1 合理判定"本段无可提取"(背景段/章节标题/空白页)被当成 L0 失败,触发不必要的 L1/L2 救援
3. **BUG#2B JSONL 严格解析丢内容**(deepseek_client.py chat_with_jsonl):R1 偶尔回退老 JSON 数组格式,被严格逐行解析丢弃 → 老唐 0428 第 2 段 958 字 0.099 元 R1 输出全丢

涉及 2 代码文件 + 4 项目文件(含 01 工程手册保守瘦身 20 行)。Phase 1-3 单对话完成。立规则 9 第 17/18 次应验 + 立规则 51 落地 + 立规则 61 新立。

### Added

- `_is_thinking_model(model)`(deepseek_client.py): 模式匹配函数,识别 `R1` / `Thinking` / `K2.6` / `K2.5` / `reasoner` 关键字(大小写不敏感),自动覆盖未来新增思考型模型
- `chat_with_jsonl` JSONL 兼容降级分支:逐行解析 0 行 + 0 _meta + content 非空 → 调用 `_extract_json_robust` 7 步保险(含 JSON 数组 / 单 dict / 截断修复全套),救回成功打印 `[JSONL 兼容降级] 7 步解析救回 N 条 kp(原本 0 行)`
- 立规则 61 新立(候选,01 §二):字符串集合 in 判等改为模式匹配函数

### Fixed

- **BUG#1 timeout 漏判**:`R1_MODELS = {"deepseek-reasoner"}` 只认一个名字 → 硅基思考型走 120s timeout 必超时。`_is_r1` 函数体改为调用 `_is_thinking_model`,3 处调用点(`_request` timeout 选择 / `chat` 跳过 temperature / `chat_continue_with_prefix` 端点选择)零破坏自动覆盖
- **BUG#2A 0 kp 误判**:`if not result["truncated"] and kps: return kps` 把 0 kp 误判为失败 → 改为 `if not result["truncated"]: ... return kps`,新增 `raw_parsed=True` 分支打印 `本段无可提取知识点(R1 合理判定,跳过救援链)`
- **BUG#2B JSON 数组输出丢弃**:R1 偶尔回退老格式被 JSON Lines 严格解析丢弃 → `chat_with_jsonl` 解析 0 行后直接复用 `_extract_json_robust` 7 步保险

### Changed

- `R1_MODELS` 集合保留作为遗留字段(向下兼容),实际判定逻辑切换为 `_is_thinking_model`,代码注释明确说明改造原因
- 控制台输出消息升级:0 条 kp 不再无脑打印 `[L0 失败]`,区分 3 类:`本段无可提取知识点(合理判定)` / `[L0 失败] R1 输出截断` / `[L0 失败] R1 输出格式异常 + 7 步降级未救回`
- **工程手册 01 保守瘦身 20 行(立规则 51 落地)**:删 §八"v2.3.4 提取截断三级降级链(D10)"整章(已被 hotfix1 5 层降级 + hotfix3 完全替代,立规则 16 §二 内文已覆盖最新形态)+ §九 review.html JS 函数清单瘦身(F062 13 个 + Tab 3 19 个函数名清单删,grep `function ` 5 秒可得;保留约束 / emoji 例外 / 状态变量 / 调用契约)。1141 → 1121 行,**契约性内容零损失**

### Migration

- **无 schema 变更,无 .env 变更,无硅基账号操作**
- **只替换 2 个 .py 文件**:`scripts/deepseek_client.py` + `scripts/extractor.py`
- **验证步骤**:勾选 1 个有截断历史的文件强制重处理,日志应看到下列任一表现:
  - 背景段/章节标题段:`本段无可提取知识点(R1 合理判定,跳过救援链)`(原本会跑 L1/L2 浪费 5+ 分钟)
  - R1 输出 JSON 数组格式:`[JSONL 兼容降级] 7 步解析救回 N 条 kp`(原本 0 提取)
  - 真截断:`[L1 Kimi 救回]` 或 `[L2 R1镜像 救回]`(原本 timeout × 9 全失败)

### 立规则应验

- **立规则 9 第 17 次应验**:hotfix1 新增硅基模型时未 grep 全 codebase 同步扩展所有 model 名字判断点(`R1_MODELS` / `_is_r1` / `model in {`),凭"硅基能调通"就推上线 → 第二天翻车。**新增模型加入降级链时必须 grep 三连**
- **立规则 9 第 18 次应验**:`if not X and Y` 形式判定容易把"X 不成立"和"Y 不存在"混淆(本次第 340 行 BUG#2A 同根),应明确分支条件,prefer `if not X: return Y(可空)` 形式
- **立规则 61 新立**:字符串集合 `in {const set}` 判等是脆弱模式,新增成员需修改集合(易漏)。改为模式匹配函数(关键字判定),新增成员不必修改集合即可自动适配
- **立规则 49 第 N 次应用**:大文件小改动用"拷贝+局部替换",extractor.py 2360 行只改 30 行,4 次 str_replace 完成

---

## [v2.3.5-part1] - 2026-04-28 (feature - 知识关系网络底座)

**定位**:**重复检测从二态判别升级为六态关系判别 + 共识聚类**。老唐反馈"同一政策在多份文件反复重申不是噪声而是重要性信号,删了就丢失追溯能力"。方案 C 彻底重设计落地:从"删冗余"翻转为"识别关系类型 + 自动建簇 + 全部保留"。三阶段拆分(part1 底座 / part2 F055+F2 联动 / part3 可视化 / part4 投标证据链),本版 part1 是底座。

涉及 7 代码文件 + 4 项目文件。Phase 3 拆 a/b 两对话(part1a 后端 / part1b 前端 + 文档)。立规则 #3 推广再次应用 + 立规则 9 第 16 次应验记入(premium_evaluator.py 凭记忆错记为 premium_judge.py)。

### Added

- **`relation_analyzer.py`**(新建,460 行,替代 `duplicate_checker.py`):六态判别(cross_file_consensus / policy_evolution / hierarchical_refinement / same_file_redundancy / conflicting / complementary)+ V3 主链 + R1 兜底(confidence < 70 升级)+ 三入口 scan_full / scan_recent / scan_incremental + 自动建簇 + status 'pending_human_review' 状态(决策 3:AI 不确定时进待研判队列)
- **3 张新表**(db_manager init_tables + setup.py Step 11 双保险): `kp_relations`(关系边,UNIQUE 三元组 + 6 态 CHECK + 4 态 status)/ `consensus_clusters`(聚类,3 类型:consensus/evolution_chain/refinement_tree)/ `cluster_members`(多对多 + role:core/branch/derivative + sequence_order)
- **2 字段追加 knowledge_points**: `relation_count`(关系参与数,UI 徽章排序用)/ `consensus_strength`(共识强度 0-100,part3 进 composite_score)
- **5 条新索引**: idx_rel_source / idx_rel_target / idx_rel_type_status / idx_cluster_type / idx_cm_kp
- **db_manager 16 个新方法**: 关系边 CRUD(5)+ 共识簇 CRUD(5)+ 簇成员(2)+ 列表读取(2)+ 立规则#3 推广 purge 封装(2:`purge_cluster_record` 级联清 cluster_members + kp_relations.cluster_id 置空 / `purge_kp_relations` 删 kp 时清关系)
- **api_server 12 个新路由 `/api/relations/*`**: groups / summary / build_consensus / build_evolution / build_refinement / merge / mark_conflict / keep_independent / manual_classify / batch / batch_keep_independent + tools/relation_full_rescan
- **`RELATION_JUDGE_PROMPT`**(prompt_templates.py): 六态判别 + V3 主 + R1 兜底,输出 confidence + cluster_suggestion + fallback_action,**默认倾向 cross_file_consensus 而非 same_file_redundancy**(政策反复重申是信号不是噪声)
- **review.html "🔗 知识关系管理" UI**: 6 类型徽章配色(🟢 共识 / 🔵 演进 / 🟣 细化 / 🟡 冗余 / 🔴 冲突 / ⚪ 互补) + 6 处理按钮 + 待研判红色边框高亮 + 角色 badge(core/branch/derivative)+ topic + strength 显示
- **工具箱 "重扫全库关系 ★" 按钮**(决策 4 老唐手动触发): operation_hook 备份 + scan_full + 弹结果摘要

### Changed

- **删 kp 三处级联清理路径加挂**(立规则#3 推广): `delete_knowledge_point` / `delete_kps_by_source_file` / `delete_extracted_kps_by_source_file` 三处统一加 DELETE FROM kp_relations + cluster_members,旧 `knowledge_relations` 简陋表(v2.0.0)清理路径保留向下兼容
- **api_server 旧 `/api/duplicate-groups/*` 路由保留**: 内部 import 从 `DuplicateChecker` 改为 `RelationAnalyzer`,旧 UI 浏览器缓存可继续运行(但读不到新表数据,UI 升级后才能看到)
- **`/api/tools/duplicate_unified`**(F049 老接口): 内部转发到 RelationAnalyzer.scan_*,前端 dpUnified 卡内文案改为"知识关系扫描(六态判别)"
- **e2e_tester.py 白名单**: `duplicate_checker.py` 7 条 → `relation_analyzer.py` 4 条,READINESS_CHECK_TARGETS 同步换名
- **review.html title + brandVersion**: v2.3.4-hotfix2 → v2.3.5-part1

### Removed

- **`scripts/duplicate_checker.py`**(543 行物理删除): 职责完全由 `relation_analyzer.py` 承接

### Migration

- **存量库**:跑一次 `首次安装.bat`(setup.py 主流程含 `_upgrade_schema_to_current`),自动 Step 11(3 表)+ Step 12(2 字段)+ Step 13(5 索引)。**幂等可重跑,新库空跑**
- **新库**:跑一次 `首次安装.bat`,`init_tables` 一步到位(已含 3 表 + 5 索引)
- **历史 8 组 duplicate_groups 待处理(决策 4)**: 老唐**先按当前 UI 处理掉,接受信息损失** — 未来批量重跑全库知识时,重扫全库关系按钮一次性重建为新表数据
- **不需配置 .env / 不需重启外部服务 / 不影响 v2.3.4-hotfix1 提取系统**

### 立规则应验

- **立规则 #3 第 2 次推广应用**:从"删 source_files 必级联 operation_events"扩展为"删 kp 必级联 kp_relations + cluster_members",`purge_<table>_record()` 模板第 2 次落地
- **立规则 9 第 16 次应验**:Claude 凭记忆把 `premium_judge.py` 错写为 `premium_evaluator.py`(不存在的文件名),老唐发现并指正。文件名 grep 5 秒可验证,凭记忆是 bug 温床
- **立规则 53 第 7 次自证**:Phase 3 工作量评估偏低 → 中途主动拆 part1a/part1b,part1a 后端独立可 curl 验证,part1b 收尾稳健
- **立规则 57 第 3 次应用**:Phase 2 grep `loadDuplicateGroups / renderDupGroup / dupBatchAI` 等定位 review.html 改造点 ~25 次工具调用,远高于"+400 行"行数估算所暗示的工具量
- **立规则 59 第 2 次应用**:Phase 1 开工 grep CHANGELOG 前 3 个版本头确认 v2.3.5 未被占用,版本号选定不撞号

---

## [v2.3.4-hotfix2] - 2026-04-28 (hotfix - 强制重处理外键约束失败 + database is locked)

**定位**:老唐想用强制重处理对照 R1 主链 vs L1/L2 救回 kp 质量,跑不动暴露的潜伏 bug 一次根治 + 顺手补朋友试用快捷入口。

诊断:`source_files` 通过 `operation_events.related_file_id` 外键被引用(db_manager.py 行 387,v2.3.0-part3 写好的事实),`PRAGMA foreign_keys=ON`(行 142)强制生效,但 preprocessor.py 3 处裸 `DELETE FROM source_files WHERE id=?` 没级联清 operation_events → 外键约束阻挡 → conn 泄漏未 ROLLBACK → WAL 写锁卡死 → 后续 AI 入库 `database is locked`。修法:db_manager 新增 `purge_source_file_record(source_file_id)` 完整封装(BEGIN IMMEDIATE + 级联清 operation_events + DELETE source_files + 失败 ROLLBACK + finally close),preprocessor 3 处替换调用,**一处修复全部入口安全**。

立规则 #3 推广(从"删 kp 必级联 annotations"扩展为"删 X 必级联 X 的所有外键引用方")。立规则 9 第 16 次应验同根 — 写代码改 SQL 删除路径前必 grep `REFERENCES <表名>` 核查全部外键引用方,凭"应该没事"裸 DELETE 是 bug 温床。同步搭车:后台 header 加"朋友试用 ↗" pill 快捷入口(零新 CSS 复用 .stat-pill.clickable)。涉及 3 代码文件 + 4 项目文件,Phase 1-3 单对话内完成。

### Added
- `db.purge_source_file_record(source_file_id)`: 级联清 operation_events + DELETE source_files,事务安全
- 后台 header `朋友试用 ↗` pill: 复用 .stat-pill.clickable,onclick window.open('/qa','_blank')
- 立规则 #3 推广(01 §二)

### Fixed
- preprocessor.py 3 处裸 DELETE FROM source_files 全部替换为 db.purge_source_file_record 调用(强制重处理 / processing|failed 物理文件丢失清理 / 未知状态清理)
- conn 泄漏 + WAL 写锁卡死根因消除(try/except/finally close 保证连接关闭与事务结束)

### Migration
- 无 schema 变更,只替换 3 个代码文件即可
- 验证:勾选"强制重新处理"曾处理过的文件,日志应显示 `已级联清理 operation_events M 条` + AI 分析 + `[OK]`,**不再有 FOREIGN KEY constraint failed 也不再有 database is locked**

---

## [v2.3.4-hotfix1] - 2026-04-28 (hotfix - 截断零提取多模型整段重提)

**定位**:v2.3.4 上线当天老唐喂料实测触发 prefix 续写主链的设计前提缺口,一次根治。第 8/10 段(611 字小段)R1 思考爆 token → partial_kps==0 → prefix 空 → 续写跳过 → F057 也无 last_excerpt 可定位 → 整段 0 提取。

诊断:任何思考型模型(R1/Kimi-Thinking/GLM-Thinking)都可能踩 max_tokens 共享上限,**跨模型概率冗余是唯一物理解**。Phase 2 经老唐三次纠正(V3 救回不行 → Qwen3-Instruct 不行 → 千问推演不行)锁定 L1 Kimi-K2.6 + L2 R1 跨厂商镜像方案。涉及 7 文件 + 4 项目文件。

### Added
- `chat_via_siliconflow()` / `chat_jsonl_via_siliconflow()`(deepseek_client.py): 硅基流动文本模型通用调用,L1/L2 共用,Authorization 复用 OCR 已配的硅基 key,思考型模型自动跳过 temperature
- `_retry_via_siliconflow()`(extractor.py): L1/L2 整段重提共用方法,接口/解析失败返 None 进入下一层
- `extracted_by_model` 字段(knowledge_points): TEXT DEFAULT 'r1' 兼容老库; `idx_kp_model` 索引走 setup.py Step 10(立规则 60 第 1 次正式落地)
- /api/dashboard `model_distribution` 字段 + Card 15 仪表盘卡 "非主链救回 kp 数"(老唐肉眼监控,>5% 提示检查 L1 模型)

### Changed
- `_extract_with_auto_split` 5 层降级链彻底重写: R1 → Kimi-K2.6 → R1 跨厂商镜像 → F057(若 partial>=1)→ 保留;每层成功的 kp 打 _extracted_by_model 标记
- `_truncation_stats` 扩字段 + `_print_truncation_stats` 输出格式升级:📊 [文件统计] 截断N / L1 救M1 / L2 救M2 / L3 兜底K / ❌ 全失败J / 知识点N / 耗时Ts
- 立规则 16 改造(R1 截断主补救从 prefix 续写改为多思考型模型整段重提)+ 立规则 60 正式条目入册

### Deprecated
- `chat_continue_with_prefix()` + `_recover_via_prefix()` + 整个 prefix 续写主链:代码完整保留,extractor 不再调用

### Migration
- 跑一次 `首次安装.bat` 自动追齐 extracted_by_model 字段 + idx_kp_model 索引(幂等)
- 可选 .env: `SILICONFLOW_TEXT_MODEL_L1=Pro/moonshotai/Kimi-K2.6` / `SILICONFLOW_TEXT_MODEL_L2=Pro/deepseek-ai/DeepSeek-R1`(默认值,候补 Kimi-K2.5 / GLM-4.7)
- 硅基流动 API key 复用现有 OCR 配置,**不需重新配置**

### 立规则应验
- 立规则 9 第 15 次:prefix 续写代码假设 partial_kps>=1 没核对真实截断场景
- 立规则 16 改造 + 60 第 1 次正式落地 + 53 第 6 次自证 + 57 第 2 次应验

---

## 早期版本精简摘要(v2.3.4 起每版 ≤ 5 行)

### v2.3.4 — 2026-04-28 (feature)
提取系统截断防御重构:R1/V3 max_tokens 显式 8192(单次 kp 数 4-7→8-13)+ chat_with_json 默认 JSON Mode + JSON Lines 输出(截断只丢 1 行)+ Chat Prefix Completion 续写主链 V3(成本降 8 倍)+ F057 降为 L2 + 控制台 📊 文件统计。**立规则 59 新立**(CHANGELOG 是版本号唯一真相源)。立规则 9 第 14 次应验。

### v2.3.3-mvp — 2026-04-25 (feature)
双客户端架构落地:后台 review.html 调试视角 + 独立 qa_public.html 1395 行物理隔离朋友试用产品页(营销首屏 + 复制双格式 + ?u=张三 朋友身份精准识别 + IP 限速 20 次/天)。db 24→25 表(+friend_quota_daily)+ qa_history.friend_tag 字段。立规则 58 / 60 新立。

### v2.3.2-hotfix1 — 2026-04-25 (hotfix)
F055 上线 4 处 bug + 1 体验:tag_config FRESHNESS_INTERVALS 不存在 → 仪表盘 500;evidence 卡片调单数路由 404 → 改复数;4 板块默认全展开 → 板块 2/4 默认折叠;isTest 默认未勾选污染 used_count → 默认 checked;朋友模式隐藏 main badge。立规则 9 第 12/13 次。

### v2.3.2 — 2026-04-25 (feature)
F055 本地问答助手首版:866 行 qa_assistant + 7 路由 + Tab 3 + 三级降级链(V3 主 → L1 重试 → L2 R1 兜底 → L3 规则)+ 4 板块通用回答(直答/依据/延伸思考/补漏)+ 朋友试用 URL 模式 + 反馈闭环。F056 单 HTML 查看器零依赖渲染 v1.0 标准 13 字段。立规则 57 首立(Phase 3 工作量 grep 预评估)。立规则 9 第 10/11 次。

### v2.3.1-hotfix1 — 2026-04-25 (hotfix + feature)
annotations.title 潜伏 bug 修复(SQL 漏字段 + 渲染层冗余引用)+ premium_exporter JSON 升级到 F056 v1.0 标准(顶层 6 字段 + KP 13 字段嵌套 + excerpt 限长 + kp-{id} 前缀 + document_id)+ validate_publish_json 校验函数(立规则 55 第 2 次落地)。立规则 9 第 8 次。

### v2.3.1 — 2026-04-24 (feature)
精品资产生产线 F2:AI 双视角判定(客户型/投标型)+ composite_score 4 因子均衡排序 + 强推 Top 15% + 批量封神 + Markdown/JSON 导出。premium_ai_cache 表 UNIQUE(kp_id,view) 覆盖式存储。立规则四连发 53/54/55/56(压缩上下文/项目文件时机/工具脚本合并/目录约定读方为准)。立规则 9 第 5-7 次。

### v2.3.0-part3.x — 2026-04-23~24 (hotfix 系列)
F062 端到端测试全闭环 + 多个 hotfix:part3.1 F061/init_tables / part3.2 仪表盘可信度 + 异步质检补跑 + 立规则 10 / part3.3 审核统计 UI 重写 + 立规则 46 / part3.4 维度⑤ confirmed 候选池 + signature 漂移 / part3.5 诊断包 Markdown 导出 + 立规则 47/48 / part3.6 三 bug 清除 + 立规则 49/50/51 / part3.7 规则精度三连改 / part3.8 白名单大扩展 + 立规则 52。

### v2.3.0-part3 — 2026-04-24 (feature)
F062 端到端健康测试 Agent 三对话拆分:路由自省 + 启动就绪 + AST 静态三维 + V3 事件语义 + 四态 issue 跟踪(pending/fixed/intermittent/ignored)+ 软提醒(>7 天淡黄 / >14 天红)。F062 三表 + 8 方法。

### v2.3.0-part2.x — 2026-04-22 (feature + hotfix)
F048 知识库体检 Agent + 系统性 bug 防护层。六维度评分 + 三层打磨降级链(L1 主链 / L2 保守 / L3 规则兜底)+ 启动就绪性自检模板。立规则 1-5 条诞生。

### v2.3.0-part1.x — 2026-04-16~18
仪表盘工具箱整体优化 + F049 智能重复检测三选一 + F059 批量重跑 + 3 张标签分布卡 + 侧边栏一级标签筛选 + part1.1 hotfix backup_manager 模块级 operation_hook。

### v2.2.3 — 2026-04-12 (hotfix)
F057 R1 截断三级补救 + F058 质检三级降级链(L0 批量 → L1 小批 → L2 逐条 → L3 规则)+ F060 关键操作强制备份(6 触发点)+ F061 历史质检补跑 + operation_events 表。

### v2.2.x — 2025
v2.2.2 重复检测合并/批量(F051-F054 多选 + 跨页全选 + F039 V3 精判)/ v2.2.1 重复组多选保留(keep_ids)/ v2.2.0 专家注解 + 经验速记 V3 结构化(F029/F045)+ 预处理 .md 缓存。

### v2.1.x — 2025
v2.1.2 长任务管理 + 版本重提取 + Tab 双视图(F046/F047)/ v2.1.1 政策依赖校验 + 重复检测(F028/F039)/ v2.1.0 三层标签体系 + 保鲜(F021-F028)。

### v2.0.0 — 2025
Flask 本地 Web 管理后台 + Tab 双视图 + 知识点 CRUD + 编辑历史追溯。

### v1.x — 2024
基础提取引擎:R1 提取 + 硅基流动 OCR + SQLite 底座。

---

## 附录:完整历史与重构说明

详细每版交付清单见 [GitHub Releases](https://github.com/Fat-designer920/rural-revitalization-kb/releases) 和 Git commit 记录。

**重构说明**(2026-04-28,v2.3.5-part1 立规则 47 再次执行):本 CHANGELOG 自 v2.3.5-part1 起严格执行"近 3 版完整 + 早期折叠 ≤ 5 行/版"格式,瘦身 673 → ~200 行(-70%)。立规则与设计决策原文档已迁移至 `01_工程手册.md`,本文件不重复。
