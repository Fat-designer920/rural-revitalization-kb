# 乡村振兴知识库搭建助手

> 基于 DeepSeek R1/V3 双模型的专业知识库构建工具，面向四川乡村振兴领域。
>
> **知识工厂**：原料 → 加工 → 质检 → 产品 → 卖钱。底座是知识库，上面长出多种产品形态。
>
> **当前版本**:**v2.3.7**(集团化重构: 7部门25个AI Agent(含研发中心9人) + CEO V4-Pro深度决策 + 会议辩论共识 + 客户画像驱动 + NPU/GPU智能调度)— 聚焦"策划+融资"垂直锚点,锚定月入20万。**核心交付**: agents/独立目录(16模块) / CEO receive_instruction()唯一入口 / 七步会议协议 / Agent验证器(4项上岗测试) / 后勤保障Agent(内存+NPU+GPU) / 客户画像研究员。历史版本:v2.3.6-part1 并行双模型提取 / v2.3.5-part2 V4-Pro全链路 / v2.3.5-part1 知识关系网络

## 集团架构(v2.3.7)

**乡村振兴知识集团** — 7部门25个AI Agent(含研发中心9人),锚定"策划+融资",月入20万目标

| 部门 | 部长 | 成员 | KPI |
|------|------|------|-----|
| CEO办公室 | CEO战略家(V4-Pro) | 财务分析师 + Agent进化师 | 方向正确、财务可控 |
| 内容生产部 | 喂料调度员 | 政策研究员 + 案例采编员 + 方法论专家 | 月产≥200条高质量KP |
| 客户交付部 | 方案汇编师(V4-Pro) | 客户视角审查员 + 问答顾问 | 满意度≥85%、续费率≥60% |
| 市场拓展部 | 获客策略师(V4-Pro) | 内容营销员 | 月新增付费≥100人 |
| 质量保障部 | 事实核查员 | 保鲜监控员 | 零事实错误、保鲜率≥95% |
| 技术平台部 | 后勤保障员 | 系统运维员 | 99.9%在线、NPU/GPU充分利用 |

**协作协议**: 老板指令 → CEO V4-Pro深度分析 → 质疑/提替代方案 → 达成共识 → 召集Agent开会辩论 → CEO裁决 → 执行

---

## 系统定位

这不是普通的文档管理工具，而是**知识工厂**——将行业文件、政策法规和 20 年实战经验加工成可变现的知识产品。

**核心竞争力**：每一条知识点都有入库质检、人工审核、政策验证、定期保鲜的完整质量链。**500 条精品级知识 > 5000 条草稿级内容**。老唐的加工（判断/注解/验证）才是付费点。

| 阶段 | 做什么 | 验证什么 |
|------|--------|---------|
| 当前(v2.3.5-part2-hotfix1 后) | **V4-Pro 全链路切换 + 截断防御 3 层架构 + 跨段补漏闭环分批化 + 标签 prompt 体系一致性根治 + 5 类系统性故障一次清除** | 单文件耗时 2-3 小时(纯 A 档 V4-Pro)/ V4-Pro 截断率 ≤5% / 跨段补漏 1-2 轮收敛 / F5 标签误杀 < 5/文件 / AI 说明完整显示 / 单文件总成本 ¥3-5 / 知识点提取 130-160 条 / mirror_v4_pro 救回比例 |
| 200 条精品+ | 政策解读文章发行业圈子 | 内容付费 |
| 300 条精品+ | 云端问答助手产品化 | C 端订阅 |
| 500 条精品+ | 投标辅助 / 培训 / 合规自检 | B 端高客单价 |

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 运行环境 | Windows + Python 3.8+（便携版，绿色免安装） |
| AI 引擎 | DeepSeek API（R1 提取 + 打磨；V3 辅助判断 + 校验 + E2E 语义 + 问答生成） |
| OCR 引擎 | 硅基流动 API（Qwen2.5-VL-72B 视觉模型） |
| 数据库 | SQLite(**28 张业务表** + 37 条索引;v2.3.5-part1 新增 kp_relations / consensus_clusters / cluster_members 3 表 + 5 索引 + 2 字段) |
| Web 界面 | Flask 本地管理后台 + 独立朋友试用产品页 /qa（严格 ES5 前端，Tab 1 知识审核 + Tab 2 系统管理 + Tab 3 智能问答[调试自用] + qa_public.html[朋友试用]） |
| 操作方式 | 管理后台为主，bat 入口辅助 |

---

## 双 API 架构

| API | 用途 | 模型 |
|-----|------|------|
| DeepSeek | 知识提取 / 打磨 / 分类 / 质检 / 预分析 / 政策扫描 / 重复判断 / 体检分析 / 打磨校验 / 问答 / E2E 语义 | deepseek-reasoner / deepseek-chat |
| 硅基流动 | 扫描件 PDF 和图片 OCR（仅 OCR，不做推理） | Qwen/Qwen2.5-VL-72B-Instruct |

---

## 快速开始

### 首次部署

```
双击 首次安装.bat
```

按提示完成 Python 环境检查、依赖安装、双 API Key 配置、数据库初始化（28 张表一次建成）。

### 日常使用

```
1. 将文件放入 data/pending/ 目录
2. 双击 启动后台.bat → 自动打开管理后台
3. Tab 2 系统管理 → 提取管理
4. Tab 1 知识审核 → 人工审核
5. Tab 2 系统管理 → 工具箱 → 定期体检打磨 / 定期 E2E 扫描
```

### Tab 2 工具箱（12 个按钮）

系统检查 / 一键备份 / 恢复备份 / 保鲜扫描 / **知识关系扫描(六态)/ 重扫全库关系 ★** / 政策补跑 / 质检补跑 / **就绪度联动（R 橙，v2.3.0-part3.2 新增）** / 审核统计 / API 费用 / **知识库体检（F048）** / **端到端健康测试（F062）**

**v2.3.5-part2 关键交付**(2026-04-30):
- **V4-Pro thinking 模式主链**:`MODEL_OPTIONS["1"] = deepseek-v4-pro`(替代 R1),max_output 8192 → 384K(47 倍),context 128K → 1M,输入价 ¥4 → ¥1.05(便宜 4 倍)。30% 截断率预期降至 ~0%。
- **跨段补漏闭环(F1 核心新功能)**:`_supplementary_extract` 新方法 + Step 5 状态机,5 轮上限 + `overall_coverage∈(完整,基本完整)` 即合格,`extracted_by_model="supplementary"` 标记区分首轮/补漏轮。
- **截断救援链 5 层 → 3 层**(立规则 16 第 4 次改造):L0 V4-Pro → L1 硅基镜像 → L2 F057 → L3 保留;Kimi 兜底链(L1.1 硅基 + L1.2 Kimi 官方)整体废弃,日志铁证 0429 三段截断 0/3 救回,真正救回都是原 L2 R1 镜像。
- **F4 P0 BUG 修复**(立规则 9 第 22 次应验):`relation_analyzer.py:330` `model=` → `model_override=`,1 字符修复 v2.3.5-part1 关系判别 100% TypeError 失败。
- **F5 标签校验 ~80% 误杀修复**:`_normalize_tag` 容错"A10" / "A10 乡村产业运营" / "A10乡村产业运营"等格式,日志中过滤数量预期从 ~5 个/kp 降到 0-1 个/kp。
- **代码净删 ~280 行**(立规则 52):`chat_via_kimi_official` + `chat_jsonl_via_kimi_official` + `_get_kimi_api_key` + `has_kimi_official` + `_retry_via_kimi_official` 共 5 方法 + KIMI_OFFICIAL 类常量 + `_truncation_stats.kimi_*` 字段。
- **立规则 63 首次正式落地(INFO-CHECK)**:Phase 1 三张清单(待补传文件 / 待 web_search / 待用户决策)清空后才进 Phase 2;Phase 3 中 review.html / config_wizard.py 未补传时透明告知后变通处理,作为 v2.3.5-part2.1 顺手清债务记入 CHANGELOG。

**v2.3.5-part1.1 关键交付**(2026-04-28):

- **修复 v2.3.5-part1 改造遗漏**:part1 改造 duplicate_checker → relation_analyzer 时,api_server.py 完整迁移但 **extractor.py 内 3 处引用未同步**(import / 实例化 / 调用),老唐 0428 部署后触发提取就 `ModuleNotFoundError` 暴露
- **修复 3 处**:第 87 行 import / 第 152 行 实例化 / 第 2234 行 Step 8 调用,RelationAnalyzer 接口 drop-in 兼容(签名 + 返回值与 DuplicateChecker 完全一致)
- **变量名 + 文案对齐**:`dup_count → rel_count`,`Step 8/8 重复检测 → 关系分析`,入库 message `疑似重复 → 疑似关系`
- **立规则 9 第 19 次应验 + 立规则 50 拉通验证升级**:第 7 项明确加 `python -c "import scripts.X"` 拉通验证(`py_compile` 只查语法不查 import 解析)
- **零 schema 变更 / 零依赖变更**:仅替换 1 个 .py 文件即生效

**v2.3.4-hotfix3 关键交付**(2026-04-28):

- **3 个独立 BUG 一次根治**:hotfix1 上线第二天老唐喂料实测翻车,救援链全军覆没 + 0 条 kp 误判 + R1 输出 0.099 元全丢
- **BUG#1 timeout 漏判修复**:`R1_MODELS = {"deepseek-reasoner"}` 只认一个名字 → 硅基思考型走 120s timeout 必超时;**新增 `_is_thinking_model()` 模式匹配函数**(R1 / Thinking / K2.6 / K2.5 / reasoner 关键字),`_is_r1` 改为调用,3 处调用点零破坏自动覆盖
- **BUG#2A 0 kp 误判修复**:`if not result["truncated"] and kps: return kps` 致命 `and kps` → 改为 `if not result["truncated"]: return kps`,0 条 kp + 解析成功 = R1 合理判定(背景段/章节标题)直接返回不进降级链,新增控制台输出 `本段无可提取知识点(R1 合理判定,跳过救援链)`
- **BUG#2B JSONL 严格解析丢内容修复**:R1 偶尔回退老 JSON 数组格式被严格逐行解析丢弃 → `chat_with_jsonl` 解析 0 行后调用 `_extract_json_robust` 7 步保险(含 JSON 数组 / 单 dict / 截断修复全套),救回成功打印 `[JSONL 兼容降级] 7 步解析救回 N 条`
- **立规则 9 第 17/18 次应验**:第 17 次 hotfix1 新增模型未 grep 全 codebase 同步扩展所有 model 名字判断点;第 18 次 `if not X and Y` 形式判定容易把"X 不成立"和"Y 不存在"混淆
- **立规则 61 新立**:字符串集合 `in {const set}` 判等是脆弱模式,改为模式匹配函数,新增成员不必修改集合即可自动适配
- **零 schema 变更 / 零 .env 变更**:仅替换 2 个 .py 文件即生效

**v2.3.5-part1 关键交付**(2026-04-28):

- **重复检测哲学翻转**:从二态判别"删冗余"升级为六态关系判别 + 共识聚类 + AI 不确定走待研判队列。**老唐反馈"同一政策在多份文件反复重申是重要性信号不是噪声,删了就丢失追溯"**,方案 C 彻底重设计落地
- **六态关系判别**:🟢 跨文件共识(多份重申=政策重要性信号,全保留)/ 🔵 政策演进(版本更迭有时序)/ 🟣 细化关系(顶层→细则→落地有父子层级)/ 🟡 同源冗余(同一文件重复段落,合并)/ 🔴 矛盾冲突(全保留+人工裁决)/ ⚪ 互补关系(角度互补独立保留)
- **`relation_analyzer.py` 新建**(460 行,替代 543 行 `duplicate_checker.py`):V3 主链 + R1 兜底(confidence < 70 升级)+ 自动建簇 + cluster_suggestion + fallback_action='human_review' 时关系标 'pending_human_review' 进待研判队列
- **3 张新表 + 2 字段 + 5 索引**:`kp_relations`(关系边,UNIQUE 三元组)+ `consensus_clusters`(聚类节点,3 类型 consensus/evolution_chain/refinement_tree)+ `cluster_members`(多对多 + role:core/branch/derivative + sequence_order)+ knowledge_points 加 relation_count / consensus_strength
- **db_manager 新增 16 方法 + 2 purge 封装**:关系边 CRUD(5)+ 共识簇 CRUD(5)+ 簇成员(2)+ 列表读取(2)+ `purge_cluster_record` / `purge_kp_relations`(立规则 #3 第 2 次推广模板)
- **api_server 新增 12 路由 `/api/relations/*`**:groups / summary / build_consensus / build_evolution / build_refinement / merge / mark_conflict / keep_independent / manual_classify / batch / batch_keep_independent + tools/relation_full_rescan
- **review.html UI 改造**:Tab 1 顶部"重复检测"区改"🔗 知识关系管理",6 类型徽章配色 + 6 处理按钮 + 待研判红色边框高亮 + 角色 badge + topic + strength 显示
- **工具箱新增"重扫全库关系 ★"按钮**(决策 4 老唐手动触发):operation_hook 备份 + scan_full + 弹结果摘要(按类型分布展示)
- **立规则 #3 第 2 次推广**:从"删 source_files 必级联 operation_events"扩展为"删 X 必级联 X 的所有外键引用方"(本次 X=knowledge_points,3 处删 kp 路径全部加挂 kp_relations + cluster_members 级联清理)
- **CHANGELOG 瘦身 76%**(673 → 163 行):立规则 47 严格执行"近 3 版完整 + 早期折叠 ≤ 5 行/版"

**v2.3.4-hotfix2 关键交付**(2026-04-28):

- **`db.purge_source_file_record(source_file_id)` 新方法**:完整级联清理 source_files 行的封装(BEGIN IMMEDIATE + 级联清 operation_events + DELETE source_files + 失败 ROLLBACK + finally close),事务安全替代裸 DELETE
- **preprocessor 3 处裸 DELETE 全部替换**:强制重处理 / processing\|failed 物理文件丢失清理 / 未知状态清理三种入口都通,根治 FOREIGN KEY constraint failed + database is locked 连环错
- **后台 header "朋友试用 ↗" pill**:点击新标签页打开 `/qa`,免每次手敲 URL,复用 `.stat-pill.clickable` 样式零新 CSS
- **立规则#3 推广**:从"删 kp 必级联 annotations"扩展为"删 kp 必级联 annotations + 删 source_files 必级联 operation_events"
- **立规则 9 第 16 次应验**:`REFERENCES source_files` 外键引用是 schema 早就写好的事实,但 preprocessor 凭"应该没事"裸 DELETE 没核查,潜伏自 v2.2.0,只在"曾经处理过的文件再走强制重处理"时触发,可观测概率低导致长期未暴露

**v2.3.4-hotfix1 关键交付**(2026-04-28):

- **5 层降级链彻底重写**:R1 → Kimi-K2.6 整段重提(硅基,256K context)→ R1 跨厂商镜像整段重提 → F057(若 partial>=1)→ 保留;**段内同步降级,不留事后批量重跑**;跨 3 模型同段全失败概率接近 0
- **废弃 prefix 续写主链**(chat_continue_with_prefix / _recover_via_prefix 标 DEPRECATED 代码保留):废弃理由 partial==0 时 prefix 空续写无法启动
- **`extracted_by_model` 字段**:每条 kp 入库带来源标记(r1/kimi/r1_mirror/f057_recovery),老唐肉眼监控非主链救回比例
- **仪表盘 Card 15 "非主链救回 kp 数"**:占比百分比 + 按模型分行 + ">5% 警示"提示文案
- **`chat_via_siliconflow(model, ...)` 通用方法**:L1/L2 复用,走 `https://api.siliconflow.cn/v1/chat/completions`,复用 OCR 已配的硅基流动 API key
- **立规则 60 第 1 次正式落地**:新字段 + 依赖索引必须放 setup.py `_upgrade_schema_to_current` Step 9/10,不放 db_manager.init_tables 统一 indexes 列表(v2.3.3-mvp 文档债务清理)

**v2.3.4 关键交付**:
- **提取系统截断防御重构**:R1/V3 max_tokens 显式设 8192(原默认 4K,翻倍输出空间,**单次稳定输出 kp 数 4-7→8-13 条**)
- **chat_with_json 默认启用 JSON Mode + 双保险**:`response_format={"type":"json_object"}` 启用 + system_prompt 的"必须 JSON"硬话保留 + 失败自动降级一次不带 mode 重试,JSON 解析成功率 ~70%→95%+
- **新增 chat_continue_with_prefix(走 beta 端点 + V3 续写)**:Chat Prefix Completion 续写截断输出,把已生成 JSON 当 prefix 让模型直接接着写,**比 F057 excerpt 定位强 10 倍 + 成本降 8 倍**(R1 4/16 元 vs V3 1/2 元/百万 token)
- **5 个提取 Prompt 输出格式改 JSON Lines + PROMPT_VERSION 升 v2.3.4**:每行 1 个独立 kp JSON,最后一行 `_meta` 元数据,**截断只丢最后 1 行**而非整份 JSON
- **截断三级降级新流程**:L0/L1 Prefix 续写(2 次)→ L2 F057 兜底(从主补救降为兜底)→ L3 保留已提取
- **D11 控制台文件级统计**:每文件提取完成时输出 `📊 [文件统计] 截断N/Prefix续写M/F057兜底K/耗时Ts/估算Y元 / Prompt v2.3.4`,老唐肉眼即看
- **立规则 59 新立**:CHANGELOG.md 是版本号唯一真相源,优先于 00_项目全景.md(本版血泪立规则,立规则 9 第 14 次应验同根)

**v2.3.3-mvp 关键交付**(2026-04-25 上线):
- **双客户端架构**:后台 review.html(调试视角)+ 独立 qa_public.html(1395 行朋友试用产品页),物理隔离 + 营销首屏 + 复制双格式 + URL `?u=张三` 朋友身份精准识别 + IP 限速 20 次/天/只成功才计数 + V3/R1 主链可选(自用调试 R1,朋友强制 V3 不烧钱)
- **新增 friend_quota_daily 表 + qa_history.friend_tag 字段 + 1 索引**(数据库 24→25 表,索引 31→32)
- **立规则 58/60 新立**:对话内不输出代码细节(只交付文件)+ 新字段依赖索引必须放 _upgrade_schema_to_current

**v2.3.2 关键交付**(2026-04-25):F055 本地问答助手首版(866 行 qa_assistant + 7 路由 + Tab 3 + 三级降级链 + 4 板块回答)+ F056 单 HTML 查看器零依赖渲染 + 立规则 57 首立(Phase 3 工作量 grep 预评估)

---

## 目录结构

```
rural-revitalization-kb/
├── scripts/
│   ├── prompts/             # Prompt 模板（31 个）
│   ├── api_server.py        # 管理后台 API（v2.3.0-part3.8，F048 8 + F062 8 + qc_rerun 3 路由 + 启动兜底 init_tables；part3.8 6 批量路由 errors 收集改造）
│   ├── extractor.py         # 知识提取引擎（v2.3.0-part3.8，含 F057/F058，part3.8 冗余迁移 import 清理-21 行）
│   ├── deepseek_client.py   # DeepSeek + 硅基流动 API 封装
│   ├── preprocessor.py      # 文件预处理 + .md 缓存（v2.3.4-hotfix2，3 处裸 DELETE → db.purge_source_file_record，事务安全）
│   ├── db_manager.py        # 数据库管理（v2.3.5-part1，28 表，新增 3 关系网络表 + 2 字段 + 16 方法 + 2 purge 封装；F048 12 + F062 9 + F2 7 + qa 6 + relations 16 方法）
│   ├── relation_analyzer.py # 知识关系六态判别 + 共识聚类（v2.3.5-part1，替代 duplicate_checker.py）
│   ├── experience_notes.py  # 经验速记
│   ├── config_wizard.py     # 配置向导
│   ├── check_system.py      # 系统检查（v2.5.2，19 项）
│   ├── e2e_tester.py        # F062 端到端测试引擎（v2.3.5-part1，~1639 行，白名单替代 duplicate_checker→relation_analyzer，DIM6 76 条）
│   ├── policy_validator.py  # 政策依赖校验
│   ├── freshness_checker.py # 保鲜扫描
│   ├── backup_manager.py    # 备份恢复 + operation_hook（6 触发点）
│   ├── review_analytics.py  # 审核统计
│   ├── tag_config.py        # 标签体系
│   ├── file_reader.py       # 多格式文件读取
│   ├── setup.py             # 初始化（v2.3.0-part3）
│   ├── upgrade_manager.py   # 架构升级
│   ├── health_checker.py    # F048 体检引擎（~1360 行）
│   ├── e2e_diagnosis_exporter.py  # F062 诊断包 Markdown 导出引擎（v2.3.0-part3.8，~1077 行，第三段按文件维度分类视图）
│   ├── static_analyzer.py   # F062 静态规则库（v2.3.0-part3.7，~720 行，规则精度三连改）
│   └── db_health_check.py   # 数据层只读体检（v1.2）
├── web/templates/
│   └── review.html          # 管理后台（v2.3.5-part1，工具箱 14 卡 + 独立 QC 进度面板 + 审核统计 6 段结构化 + 7 批量按钮混合策略 + #batchResultModal + Tab 1 知识关系管理 6 类型徽章+6 处理按钮+待研判红色高亮）
├── data/                    # 数据目录
├── backups/                 # 备份目录
├── config/                  # 配置文件
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
3. **经验库**（差异化资产 —— 老唐 20 年实战沉淀）
4. **工具库**（可复用模板）
5. **数据库**（数据支撑）

### 三层标签体系

- **第一层 分类标签**：6 组 41 个（业务领域 / 项目阶段 / 知识形态 / 客户视角 / 稀缺度 / 内容状态）
- **第二层 属性标签**：8 个维度
- **第三层 关键词**：AI 自由提取 5-15 个

详见 `02_知识体系.md`。

---

## 迭代路线

| 版本 | 定位 | 状态 |
|------|------|------|
| v1.0 ~ v2.2.3 | 基础 → 提取 → 管理 → 资产沉淀 → 质量管控 | ✅ |
| v2.3.0-part1 / 1.1 | 工具箱整体优化 + hotfix | ✅ |
| v2.3.0-part2 | F048 知识库体检 Agent | ✅ |
| v2.3.0-part2.1 | schema 单一来源 hotfix | ✅ |
| v2.3.0-part2.2 | F048 四类系统性 bug 防护层 hotfix | ✅ |
| v2.3.0-part3 | F062 端到端健康测试 Agent 全闭环 | ✅ |
| v2.3.0-part3.1 | hotfix：F061 质检补跑签名漂移 + F062 老库自动追齐 | ✅ |
| v2.3.0-part3.2 | hotfix：仪表盘 UI + 质检补跑异步化 + 就绪度联动预埋 | ✅ |
| v2.3.0-part3.3 | hotfix：审核统计 UI 重写 + 保鲜 loading + 体检无低分提示 + E2E 白名单刷新 | ✅ |
| v2.3.0-part3.4 | hotfix：低分打磨允许 confirmed + E2E issue 签名漂移修复 | ✅ |
| **v2.3.0-part3.5** | **feature:E2E 诊断包 Markdown 导出(发给 Claude 做异地诊断)** | ✅ |
| **v2.3.0-part3.6** | **hotfix:诊断包三 bug 修复 + 新立规则 49/50/51(工程纪律三条:拷贝替换 / 改完拉通 / 更新做减法)** | ✅ |
| **v2.3.0-part3.7** | **hotfix:F062 规则精度三连改(silent_except/except_print_only snippet 行号对齐 body 真实行 + field_unknown 变量名收窄 + prompt_wrong_key 历史 key 白名单)+ 诊断包第三段口径与第四段对齐** | ✅ |
| **v2.3.0-part3.8** | **hotfix:F062 白名单大扩展(7 文件)+ 6 批量路由 errors 收集 + 冗余代码清理 + 立规则 52** | ✅ |
| **v2.3.1** | **feature:精品资产生产线(F2 双视角 AI 判定 + composite_score 排序 + 批量封神 + 精品 Markdown/JSON 导出)+ 立规则 53-56** | ✅ |
| **v2.3.1-hotfix1** | **hotfix:annotations.title bug + premium_exporter F056 v1.0 升级 + validate_publish_json 校验函数;立规则 9 第 8 次应验** | ✅ |
| **v2.3.2** | **feature:F055 本地问答助手首版(866 行 qa_assistant + 7 路由 + Tab 3 + 三级降级链 + 4 板块回答 + 朋友试用模式)+ F056 单 HTML 查看器(零依赖渲染 v1.0 标准 13 字段)+ 立规则 57 首立 + 立规则 9 第 10/11 次应验** | ✅ |
| **v2.3.3-mvp** | **feature:双客户端架构(后台调试 + qa_public.html 朋友试用产品页 1395 行)+ friend_quota_daily 表 + qa_history.friend_tag + 立规则 58/60 新立** | ✅ 2026-04-25 |
| **v2.3.4** | **feature:提取系统截断防御重构(R1/V3 max_tokens 8192 + JSON Mode + Chat Prefix Completion 续写主链 + JSON Lines 输出 + F057 降为 L2 兜底 + 控制台 📊 文件统计)+ 立规则 59 新立(CHANGELOG 是版本号唯一真相源)+ 立规则 9 第 14 次应验** | ✅ 2026-04-28 |
| **v2.3.4-hotfix1** | **hotfix:截断零提取多模型整段重提(废弃 prefix 续写主链 + L1 Kimi-K2.6 + L2 R1 跨厂商镜像 + F057 降为 L3 + extracted_by_model 字段 + 仪表盘 Card 15)+ 立规则 16 改造 + 9 第 15 次应验 + 60 第 1 次正式落地** | ✅ 2026-04-28 |
| **v2.3.4-hotfix2** | **hotfix:强制重处理 source_files 外键约束失败 + database is locked 连环修复(preprocessor 3 处裸 DELETE → db.purge_source_file_record 完整封装)+ 后台朋友试用快捷入口 pill + 立规则#3 推广 + 立规则 9 第 16 次应验** | ✅ 2026-04-28 |
| **v2.3.5-part1** | **feature:知识关系网络底座(替代二态重复检测的六态关系判别 + 共识聚类 + 待研判队列)— relation_analyzer.py 替代 duplicate_checker.py + 3 新表 + 2 字段 + 12 路由 + 立规则 #3 第 2 次推广** | ✅ 2026-04-28 |
| **v2.3.4-hotfix3** | **hotfix:提取链 3 BUG 一次根治(timeout 漏判 + 0 kp 误判 + JSONL 严格解析丢内容)— `_is_thinking_model` 模式匹配 + `_is_r1` 改造 + `chat_with_jsonl` 7 步保险降级 + extractor 第 340 行 `and kps` 删除 + 立规则 9 第 17/18 次 + 61 新立** | ✅ 2026-04-28 |
| **v2.3.5-part1.1** | **hotfix:part1 改造遗漏修复 — extractor.py 第 87/152/2234 行 duplicate_checker → relation_analyzer 同步迁移 + 文案对齐"关系分析"+ 立规则 9 第 19 次 + 50 拉通验证升级** | ✅ 2026-04-28 |
| v2.3.5-part2 | feature:F055 问答助手联动(依据卡片改为关系链证据 + 关系上下文召回) | 规划 |
| v2.3.5-part3 | feature:F2 精品 + F056 导出联动(composite_score 加 consensus_strength + JSON 加 relations) | 规划 |
| v2.3.5-part4 | feature:Tab 4 知识关联网络可视化 + 投标证据链生成器 | 规划 |
| v2.4.0+ | 内容生产 / 采集（按需） | 远期 |
| v3.x | 云端产品化 | 远期 |

详见 `CHANGELOG.md`。

---

## 协作流程

### 五阶段迭代工作流

1. **需求提交** → 老唐描述问题
2. **影响范围评估** → Claude 给修改逻辑 + 决策建议
3. **代码交付** → 完整文件 + 项目文件全量更新 + 操作清单
4. **用户执行** → 备份 → 替换 → 推送 → 更新 Projects → 验证
5. **回滚** → 有问题新开对话

### Claude Projects 6 个项目文件

- `00_项目全景.md`：模块状态 / 迭代路线 / 商业化 / **新对话启动指南**
- `01_工程手册.md`：代码清单 / 立规则（**59 条**，分 4 类）/ 架构速查 / 模块结构 / **未来扩展指南**
- `02_知识体系.md`：分类 + 三层标签 + **v2.3.2 问答历史元数据**
- `03_Prompt手册.md`：**31 个 Prompt** 清单与接口契约
- `CHANGELOG.md`：近 3 版完整 + 早期摘要
- `README.md`：本文件

### GitHub 仓库

https://github.com/Fat-designer920/rural-revitalization-kb

---

## 关键约束（改代码时必读）

> 完整立规则见 `01_工程手册.md` §二（分数据层 / 代码层 / 交互层 / 流程层 4 类 59 条）。以下是高频命中项：

**环境约束**：
- **bat 文件**：GBK 编码 + CRLF 换行；不在 Python `-c` 参数内用 `%~dp0`
- **review.html**：零 emoji + 严格 ES5（无箭头函数、无 const/let、无 async/await、无模板字符串）
- **Flask**：`Response(html, mimetype="text/html; charset=utf-8")` 返回，不用 `render_template()`
- **R1 调用**：不传 temperature，不传图片，超时 300 秒，分段 ≤ 3000 字
- **OCR**：用硅基流动不用 DeepSeek

**数据约束**：
- **删除知识点必手动级联 annotations**（外键无 CASCADE）
- **schema 单一来源**：`init_tables()` 是唯一建表真相，migrate 脚本升完即退役
- **api_server 启动兜底 init_tables**（v2.3.0-part3.1 起）：避免老库缺新表
- **字段真名**：kp 表外键是 `final_category_id` 不是 `category_id`
- **存储/查询口径一致性**（v2.3.0-part3.2 起）：JSON 字段新增 SQL 查询前，必须对照存储侧写入逻辑确认存的是 name / code / 中文 / 英文 / 扁平列表 / 嵌套
- **筛选条件边界对齐业务现状**（v2.3.0-part3.4 起）：WHERE 子句的过滤条件过段时间后可能不符业务现状，业务流程变化（如就绪度联动上线）时必须回头校对所有依赖该状态字段的查询

**流程约束**：
- **长任务启动就绪性自检必须在 `_task_lock` 之前**（独立任务槽也要对齐这个模板）
- **6 个关键操作触发点必须先 `operation_hook(op_name)` 备份**
- **`_task["type"]` 前后端字面锁定**：F048 用 `"health"`，F062 用 `"e2e"`；独立任务槽（如 part3.2 的 `_qc_task`）不占用 `_task["type"]` 映射
- **跨版本调用外部模块方法前必须对照真实签名**（v2.3.0-part3.1 起铁律）：`grep -n "def <方法名>"` 查源码，不相信记忆不相信旧文档。part3.4 第三次应验（`upsert_e2e_issue` 漂移）

**AI 调用约束**：
- **Prompt 双 key 严格**：`system_prompt` / `user_prompt_template`
- **severity 严格三态**：`info` / `warning` / `error`（禁 `warn` 简写）
- **禁止包级静默降级**（try/except 顶层 import + None 兜底）

**前后端契约约束（v2.3.0-part3.3 起）**：
- 后端升级 API 返回结构时，前端所有消费点必须同步升级渲染逻辑
- 兜底 `if(!h) showToolResult(pre(JSON))` 是临时救命草不是长期方案

**质检铁律（v2.2.3）**：
- 每条知识点必须有 `qa_score + qa_source`
- 三级降级链：L0 批量 → L1 小批 → L2 逐条 → L3 规则兜底

**就绪度联动（v2.3.0-part3.2 保守预埋，v2.3.1 补齐完整版）**：
- 规则：`qa_score >= 4 AND content_readiness='draft' → 'quotable'`
- 只升不降，不碰 `premium`（editorial 轴与 qa 轴解耦）
- 质检补跑尾部自动触发；也可通过工具箱"就绪度联动"按钮手动触发

---

## 变更日志

详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 许可证与支持

本项目为个人实战资产沉淀工具，当前阶段仅供老唐本人使用。未来商业化路径见 `00_项目全景.md`。
