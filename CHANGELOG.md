# CHANGELOG

> 乡知·乡村振兴AI助手 — 版本变更记录

---
## [v2.3.7-part6-fix1] - 2026-05-07 (bugfix)

**Fixed**:
- .bat文件编码: 首次安装.bat + 启动后台.bat 从 UTF-8 without BOM 转为 UTF-8 BOM, 中文 Windows cmd.exe (GBK) 不再乱码
- 窗口标题: 禁用 cmd `title` 命令, 改用 Python `SetConsoleTitleW()` Unicode API 设标题

**Added**:
- 立规则 #81: .bat编码铁律 (UTF-8 BOM + SetConsoleTitleW)

---
>
> 格式:近 3 版完整 Added / Fixed / Changed / Migration 四段式;早期版本折叠为单段摘要(每版 ≤ 5 行)。立规则与架构契约统一沉淀在 `01_工程手册.md`,本文件不重复。完整历史见 [GitHub Releases](https://github.com/Fat-designer920/repo/releases)。

---
## [v2.3.7] - 2026-05-05 (feature - 集团化重构: 6部门16Agent + CEO会议决策 + 客户画像驱动)

**定位**: v2.3.7是本项目从"单体脚本集"升级为"集团公司AI Agent体系"的架构级重构。核心变化: (1) agents/独立目录,15个Agent模块物理隔离于scripts/核心管道; (2) 从31个Agent精简为16个,按6部门组织(CEO办公室/内容生产/客户交付/市场拓展/质量保障/技术平台); (3) CEO从"if-else轮询"升级为"V4-Pro深度决策+会议辩论+共识裁决"; (4) 所有Agent从静态配置字典升级为BaseAgent思考实体,每个都能独立调用AI API; (5) 15个角色Agent合并为1个客户视角审查员,加载CustomerProfiler真实画像库。

**Added**:
- `agents/` 目录(16个模块): base_agent.py(BaseAgent/RoleAgent/QualityAgent/StrategyAgent四级类体系), ceo_agent.py(receive_instruction入口+会议决策+Git推送+CLAUDE.md维护+动态Agent增删), meeting_engine.py(七步会议协议: 独立表态→强制异议→AI主持→CEO裁决), agent_verifier.py(4项上岗验证: 专业度+独立性+盈利导向+抗盲从), customer_profiler.py(客户画像研究: 搜索→验证→构建→交付审查员), infrastructure_agent.py(后勤保障: 内存监控+NPU/GPU路由+自动清理+动态批处理), agent_orchestra.py(16Agent按6部门组织), crawler_scheduler.py(真实HTTP爬取实现)
- CEO协作协议: 老板指令→CEO V4-Pro深度分析→质疑/提替代方案→达成共识→才执行
- 盈利导向注入: 所有Agent system_prompt注入"忠诚=集团利润,禁止迎合任何人,KPI=可持续收入"
- 组织架构API: /api/agents/org-chart, /api/agents/status(六部门), /api/agents/infra-* (3条)

**Changed**:
- 31 Agent → 16 Agent (15 orchestra + 1 infrastructure), 15个角色Agent合并为1个客户视角审查员
- agent_orchestra.py: 从返回dict列表 → 返回BaseAgent实例+部门定义
- company_agents.py: 6个公司Agent → 功能吸收到六部门,返回空列表
- ceo_agent.py: _strategize()从单人V4-Pro决策 → 召集Agent会议→辩论→CEO裁决
- auto_tester.py: reader_tagger/audit_engine路径 scripts→agents
- api_server.py: +11条Agent路由(ceo/agents/infra/verify/meeting)
- review.html: +3个工具箱卡片(CEO Agent/Agent智慧体系/Agent审计)

**Removed**:
- 13个Agent冷冻(代码保留): 15个独立角色Agent→1个; 渠道/定价/上线/客服Agent→财务分析师+方案汇编师覆盖
- scripts/下15个agent文件物理删除(已迁移到agents/)

**Migration**:
- 数据库无schema变更
- 老用户: 替换全部agents/目录+scripts/api_server.py+scripts/auto_tester.py+scripts/extractor.py(reader_tagger import路径更新)
- 新对话Claude必须读CLAUDE.md第0步(已更新agents/架构描述)


## [v2.3.6-part1] - 2026-05-01 (feature - 并行双模型架构:V4-Flash 全覆盖 + V4-Pro 深挖核心段)

**定位**:本版是提取引擎从"单思考型深度提取"升级为"速度+质量双目标并行"的架构重构。**V4-Flash 快速全覆盖所有段落 + V4-Pro 深挖核心段(标题+关键词段)→ 合并去重**,解决"提取太多(211 条)"和"提取太久(3.7 小时)"的深层矛盾。跨段补漏从 5 轮缩减到 1 轮。老代码已预先开发(确认保留),本版正式文档化和版本化。

**Added**:
- `scripts/extractor_parallel.py`(135 行): `identify_core_segments(file_structure, segs)` 识别标题段+关键词段 + `merge_and_deduplicate(flash_kps, pro_kps)` 合并去重(Core 优先 + >85% 相似度保留更长 excerpt + `_title_similarity` bigram Jaccard)
- `_extract_with_flash()(extractor.py`:临时切 V4-Flash 全段提取) / `_extract_with_pro()`(V4-Pro 深挖核心段) / `_identify_core_segments()` / `_merge_and_deduplicate()` 共 4 方法
- `_truncation_stats` 新字段: `parallel_flash_kps` / `parallel_pro_kps` / `merged_duplicates`

**Changed**:
- **Step 4 逐段提取重写**:从单 V4-Pro 逐段 → 并行双模型(V4-Flash 全覆盖 + V4-Pro 核心段)→ 合并去重后再进 Step 5
- `CHECK_MAX_ROUNDS = 5 → 1`:Flash 全覆盖 + Pro 深挖核心段已覆盖绝大多数,1 轮补漏足够
- `MODEL_OPTIONS["1"] segment_max = 3000 → 6000`:V4 的 1M context 支持更大分段,减少分段数量降低总耗时
- 跨段补漏覆盖度阈值同步收紧(与 Flash+Pro 双覆盖配合)

**Migration**:
- 数据库零变动
- 老用户:替换 extractor.py + 新增 extractor_parallel.py(2 文件)
- **分段数预期减少**(6000 字/段原 3000),耗时大幅下降

---

## [v2.3.5-part2-hotfix1] - 2026-04-30 (hotfix - V4-Pro 全链路切换 + 5 类系统性根因一次清除)

**定位**:本版是 v2.3.5-part2 部署后老唐 0430 喂料实测 1 个文件暴露的 5 类系统性故障一次性根治。**主链 V4-Pro 升级范围补完**(part2 只切了主提取,本版补预分析/结构摘要/跨段补漏/质检/分类建议/关系判别共 7 处)+ **降级链 max_tokens 升级**(L1 硅基镜像 8192→32768 + 主提取 32768→65536,留 V4-Pro thinking headroom)+ **跨段补漏分批化**(>30 条 kp 自动按 30/批分,避免 coverage_analysis 输出超 max_tokens 中止闭环)+ **标签 prompt 与校验体系一致性**(5 个 _EXTRACT_BASE 老 1.X-5.X 编号清单删除 + _normalize_tag 加近义子串兜底)+ **AI 说明显示 80→300 字 + 多处 R1 文案改 V4-Pro/通用**。**立规则 9 第 23 次应验**(同根:升级主链时只看主链,L1 max_tokens=8192 没改、L1 model 没升、跨段补漏 max_tokens 默认 8192、5 个 _EXTRACT_BASE 老 1.X 清单同样体系不一致)。

**Added**:
- `extractor.py::CROSS_CHECK_BATCH_SIZE = 30` 类常量 + `_cross_segment_check_single_batch` 新方法(分批模式 helper)
- `extractor.py::_normalize_tag` Case 5 近义子串匹配兜底(双向 substring 包含,len ≥ 4 才走避免短词误匹)
- `deepseek_client.py::siliconflow_mirror_model` 实例属性(读 `settings.json::siliconflow_mirror_model`,空值回退类常量)
- `deepseek_client.py::SILICONFLOW_TEXT_MODEL_FALLBACK = "Pro/deepseek-ai/DeepSeek-R1"` 类常量(V4-Pro 镜像不可用时兜底)
- `extracted_by_model` 新取值 `"mirror_v4_pro"`(替代 `"r1_mirror"`,体现 L1 默认模型升级)
- `relation_analyzer.py` 关系判别 confidence 低时 `fallback_action="human_review"` 写入待研判队列(替代原 V3→R1 二次升级)

**Fixed(根因 5 类)**:
- **A1-A6 类:V4-Pro 切换不彻底**(立规则 9 第 23 次应验子项 1):0430 实测预分析 0.0022 元 = V3 价格,确证 part2 仅主提取切了 V4-Pro。本版补全 6 处 model_override:`extractor.py:1014/1055/1342/1525/1557/2064`(预分析/结构摘要/跨段补漏/质检批量/质检单条/分类建议)及 `relation_analyzer.py:274/281/301`(关系判别主链 + 取消 R1 二次升级走 human_review)
- **B2 类:V4-Pro thinking 输出截断**(L0 失败 4/10 段):V4-Pro thinking 模式 reasoning_content 与 content 共享 max_tokens 配额,32K 在某些段被思考链吃光致 JSONL 输出 0 行。修法:主提取 max_tokens 32768 → 65536(留思考链 30K headroom 给输出 35K)
- **C1 类:第 7 段 L0+L1 全失败**(立规则 9 第 23 次应验子项 2):L1 硅基镜像 R1 走 max_tokens=8192(v2.3.4-hotfix1 hardcode 没在升级时同步),思考型 8K 全被思考吃光。修法:`_retry_via_siliconflow` max_tokens 8192 → 32768 + L1 默认 model 从 R1 镜像升 V4-Pro 镜像
- **D1 类:跨段补漏闭环中止**(0430 调试 txt 实证 V4-Flash 输出 3782 字符 ≈ 7000 token 截断在`鼓励测土配方施肥与增施有机肥`):chat_with_json 默认 max_tokens=8192,109 条 kp 的 coverage_analysis 输出超额。修法:(a) max_tokens 显式传 32768;(b) kp 数 > 30 时按 30/批 分批检查,合并 missed_sections(按 section_title 去重)+ duplicate_suspects 合并 + overall_coverage 严重度优先投票(严重遗漏 > 有遗漏 > 基本完整 > 完整);(c) model 从 V4-Flash 升 V4-Pro
- **E1+E2+E3 类:F5 标签 ~40 处误杀**(根本性历史债务):`prompt_templates.py` 5 个 `_EXTRACT_BASE` 的 user_prompt_template 硬编码"可用分类:1.1...1.7 / 2.1-2.6 / 3.1-3.5 / 4.1-4.6 / 5.1-5.5"老 v2.1.1 编号清单,但 `tag_config.LAYER1_TAGS` 真实清单已是 A/B/C/D/E/F+数字 体系 → 模型按老体系输出"1.6乡村振兴综合政策",F5 校验按新体系查不到全部过滤。F5 v2.3.5-part2 修了"格式不一致"但没修"体系不一致"。修法:(a) 5 处老编号清单整行删除(`_build_tag_reference` 注入的真实 LAYER1 清单是唯一真相);(b) 5 处字段说明"如1.1" → "从 LAYER1 清单中选";(c) `_normalize_tag` 加 Case 5 近义子串匹配兜底
- **F1 类:AI 说明 print 截断**(0430 实测第 2/10 段 80 字被腰斩):`extractor.py:329` `notes[:80]` → `notes[:300]`
- **G1+G2 类:R1 文案残留**:预估费用文案"R1提取约 + V3辅助" / 控制台"R1输出被截断" / "R1原始返回" / F057 prompt"本段因R1输出截断" / `_estimate_extraction_cost` docstring + 单价 ¥4/¥16 → V4-Pro ¥1.05/¥12.5 + 单段 output 估算 1500 → 5000 token(thinking 含思考链)

**Changed(立规则 9 第 23 次应验同根 + 立规则升级)**:
- 主提取 `chat_with_jsonl` max_tokens 32768 → 65536(给 V4-Pro thinking 30K + 输出 35K headroom)
- L1 硅基镜像兜底:max_tokens 8192 → 32768 + model 默认值 R1 镜像 → V4-Pro 镜像(`SILICONFLOW_TEXT_MODEL_L2`)+ extracted_by_model 标记 `r1_mirror` → `mirror_v4_pro`
- 跨段补漏 model `deepseek-v4-flash` → `deepseek-v4-pro`,默认 max_tokens 8192 → 32768
- 跨段补漏架构:单批模式 → 单批 / 分批双模式(>30 条自动分批)
- 关系判别主链 `deepseek-chat` → `deepseek-v4-pro`,confidence 低不再二次升级 R1(同思考型重跑无意义),改写 `fallback_action=human_review` 进待研判队列
- 5 个 `_EXTRACT_BASE` 删除老 1.X-5.X 编号体系硬编码清单,统一由 `_build_tag_reference()` 动态注入真实 LAYER1_TAGS
- `PROMPT_VERSION` v2.3.5-part2 → v2.3.5-part2-hotfix1
- 立规则 9 第 23 次应验入档 + 立规则升级:**改造主链时必须同步扫降级链 max_tokens / model_id / 标记字段三处**(grep 维度补充)
- 立规则 16 第 5 次改造确认:V4-Pro 主链 + 硅基 V4-Pro 镜像兜底(跨厂商物理冗余仍成立,立规则 62 通过)
- 立规则 53 第 9 次自证(本版 Phase 3 中途因配额顾虑发出"喊停拆对话"建议,老唐"继续"督促才在原对话内完成全 4 文件 + 5 项目文件;立规则 53 教训记入 — 配额顾虑不是合法 break 理由)
- 立规则 57 第 4 次应用:跨段补漏 D1 大改造工作量被低估(估 5 次 str_replace,实际带连锁改动 ~10 次),教训:"大改造"应给加权 2-3 倍

**Migration**:
- 数据库零变动(本版无 schema 改动)
- 老用户:替换 4 文件即可(extractor / deepseek_client / relation_analyzer / prompt_templates)
- **可选 settings.json 新字段**:`siliconflow_mirror_model`(字符串,默认值 `Pro/deepseek-ai/DeepSeek-V4-Pro`)— 老唐查到硅基真实 V4-Pro 模型 ID 后填入即生效;不填或空字符串自动用类常量默认值;若硅基暂无 V4-Pro 老唐可手动填 `Pro/deepseek-ai/DeepSeek-R1` 暂回退到 R1 镜像
- 已入库 kp 的 `extracted_by_model="r1_mirror"` 不需迁移(历史标记保留可读性);新入库 L1 救回 kp 标记 `mirror_v4_pro`

**单文件预期效果**(改完后,实测前理论估算):

| 指标 | v2.3.5-part2 实测 | hotfix1 预期 |
|------|------------------|-------------|
| L0 V4-Pro 截断率 | 4/10 段(40%) | ≤ 5%(max_tokens 65536 + thinking headroom) |
| 第 7 段类 L0+L1 全失败 | 偶发 | 0(L1 max_tokens 32K + V4-Pro 镜像) |
| 跨段补漏闭环 | 中止(8K 装不下 109 kp) | 1-2 轮收敛(分批 + 32K) |
| F5 标签误杀 | ~40 处/文件 | < 5 处/文件(体系一致 + 子串兜底) |
| AI 说明显示完整度 | 80 字截断 | 300 字基本不截 |
| 单文件耗时 | 60 分钟 | 2-3 小时(全 V4-Pro thinking,纯 A 档) |
| 单文件成本 | ¥1.2(part2 仅主链 V4-Pro) | ¥3-5(全 V4-Pro 含质检批量) |
| 知识点提取数 | 109 条 | 130-160 条(V4-Pro 推理深 + 补漏闭环救回) |

---

## [v2.3.5-part2] - 2026-04-30 (feature + hotfix - V4-Pro 主链 + 跨段补漏闭环 + Kimi 兜底链全删 + F4/F5 修)

**定位**:本版是知识工厂"批量跑知识"前的最后一次系统性重构 — 主链从 R1 升级到 V4-Pro thinking 模式(384K max_output 直接根治 30% 截断率),跨段补漏从"建议老唐审核时关注"升级为"自动 5 轮重提取闭环",Kimi 兜底链(L1.1 硅基 Kimi / L1.2 Kimi 官方)整体废弃 — 0429 实测 L1.1+L1.2 三段截断 0/3 救回,真正救回都是 L2 R1 镜像。降级链 5 层简化为 3 层。同时修复 F4 关系判别 100% 失败的 P0 BUG(立规则 9 第 22 次应验)+ F5 标签校验 ~80% 误杀的格式不兼容问题。

**Added**:
- `extractor.py::_supplementary_extract` 新方法 — 针对跨段补漏检查发现的高/中重要性 missed_sections 自动重新提取 kp,V4-Pro 1M context 装得下完整原文 + 已提取标题清单,无需切片
- `extractor.py::_normalize_tag` classmethod — 标签字符串标准化函数(剥离 code 前缀 + code↔name 双向映射),`LAYER1_CODE_TO_NAME` / `LAYER1_NAME_TO_CODE` 类常量
- `MODEL_OPTIONS["1"]` 升 V4-Pro / `["2"]` 升 V4-Flash;`["1_legacy"]` / `["2_legacy"]` 保留旧 R1/V3 作"逃生回滚"档
- `PRICING` 加 `deepseek-v4-pro` / `deepseek-v4-flash` 价格
- `_truncation_stats` 加 `supplementary_rounds` / `supplementary_kps_added` 字段(文件级闭环统计)
- `extracted_by_model` 新取值 `"supplementary"`(供审计区分首轮 vs 补漏轮 kp)

**Fixed**:
- **F4 P0 BUG(立规则 9 第 22 次应验)**:`relation_analyzer.py:330` 调 `chat_with_json` 用了不存在的 `model=` 关键字,真实签名是 `model_override=`,老唐 0429 实测 7 组关系判别全部 TypeError 失败 → v2.3.5-part1 主功能瘫痪。修法:1 字符 `model` → `model_override`,同时把"reasoner not in model"思考型判定升级为支持 V4-Pro
- **F5 标签校验 ~80% 误杀**:`_sanitize_tags` 从 strict equality `t in VALID_LAYER1_NAMES` 升级为 `_normalize_tag` 容错,AI 输出 `"A10"` / `"A10 乡村产业运营"` / `"A10乡村产业运营"` 等格式都映射到合法 name,日志中过滤数量预期从平均 5 个/kp 降到 0-1 个/kp

**Changed(立规则 16 改造 + 立规则 61 第 2 次应用)**:
- 截断救援链 5 层 → 3 层:`L0 V4-Pro → L1 硅基镜像兜底 → L2 F057 → L3 保留`(原 L1.1 硅基 Kimi / L1.2 Kimi 官方 / L2 R1 镜像 三层合并为新 L1)
- 删除 `extractor.py::_retry_via_kimi_official` 整方法(78 行)
- 删除 `deepseek_client.py::chat_via_kimi_official` + `chat_jsonl_via_kimi_official` 两大方法(149 行)
- 删除 `deepseek_client.py::_get_kimi_api_key` + `has_kimi_official` 两方法 + `KIMI_OFFICIAL_ENDPOINT` / `KIMI_OFFICIAL_MODEL_L1` 类常量
- 删除 `_truncation_stats` 中 `kimi_recoveries` / `kimi_official_recoveries` 字段
- `_is_thinking_model` 加 `"v4-pro"` 关键字(V4-Pro 默认 thinking 模式,自动跳 temperature + 走 300s timeout)
- `_cross_segment_check` model 从 `deepseek-chat` → `deepseek-v4-flash`
- 主提取 `chat_with_jsonl` 显式传 `max_tokens=32768`(充分利用 V4 输出能力,V4 上限 384K)
- `_print_truncation_stats` 简化字段(去 Kimi 输出 + 加跨段补漏轮数)
- `Step 5 跨段补漏检查` 改造为状态机闭环(5 轮上限 + 基本完整即合格)

**Migration**:
- 数据库零变动(extracted_by_model 字段 v2.3.4-hotfix1 已加,新取值 `supplementary` 复用现字段)
- 老用户:替换 6 文件即可(无需重跑 `首次安装.bat`)
- `settings.json` 中老用户的 `kimi_official_api_key_encrypted` 字段保留无害,代码不再读取
- **首次启动喂料前先验证**:`python -c "from scripts.deepseek_client import DeepSeekClient; c=DeepSeekClient(); r=c.chat('你是助手','说你好',max_tokens=200,model_override='deepseek-v4-pro'); print(r['content'][:50])"`,看是否返回 V4 正常响应

**已知小债务(v2.3.5-part2.1 顺手清)**:
- `web/templates/review.html` Card 15 文案仍显示旧字段(L1.1 硅基 Kimi 救 / L1.2 官方 Kimi 救 / L2 R1 镜像救),后端不再推这些字段 → Card 显示 0(不会崩,UX 略奇怪)
- `scripts/config_wizard.py` 第 5 项"Kimi 官方 API Key"输入仍存在,新用户走配置向导多答一个无效问题
- 两项都是纯 cosmetic,不影响功能,下版顺手清

**立规则联动**:
- **立规则 16 改造(本版第 4 次)**:截断兜底链从"5 层(R1→Kimi硅基→Kimi官方→R1镜像→F057)"改为"3 层(V4-Pro→V3.2镜像→F057)"。Kimi 物理冗余目标实测不达预期(L1.1+L1.2 三段全失败),V4 max_output 47 倍于 R1 直接根治截断,从源头消除"必须思考型概率冗余"的需求
- **立规则 61 第 2 次应用**:`_is_thinking_model` 加 `"v4-pro"` 关键字 — 字符串模式匹配函数自动适配 V4 思考型,无需修改任何调用点,完美自证"集合 in 判等→模式匹配函数"的设计优势
- **立规则 62 仍成立**:V4-Pro 主链走 `api.deepseek.com` / 镜像兜底走 `api.siliconflow.cn`,跨厂商物理冗余仍是两个独立故障域
- **立规则 63 首次正式落地**:Phase 1 信息齐全度自检 INFO-CHECK,本版 Phase 1 输出三张清单(待补传文件 / 待 web_search / 待用户决策)清空后才进 Phase 2;Phase 3 中 review.html / config_wizard.py 未补传时透明告知后变通处理(不假设、不猜代码)
- **立规则 9 第 22 次应验**:relation_analyzer 凭记忆写 `chat_with_json(model=...)` 关键字,真实签名是 `model_override=`。已成立的 22 条应验,根因都是"写代码靠记忆不 grep 真实签名"
- **立规则 53 第 8 次自证**:Phase 3 中途 Claude 又一次"工具配额顾虑"喊停拆对话,老唐"继续"督促才一气呵成完成。立规则 57 工作量预评估对单次大段 str_replace 应给加权(整段 docstring 重写 = 3 次普通 str_replace 配额),记入 v2.3.5-part2 的工程纪律债务

---

## [v2.3.5-part1.3] - 2026-04-29 (hotfix - L1 救援链跨厂商物理冗余:硅基 → Kimi 官方双 L1 互备)

**完整条目内容已迁移至 v2.3.5-part2 上方诸条**(立规则 51 做减法 — part1.3 引入的 Kimi 兜底链在 v2.3.5-part2 整体废弃,具体改动详情已被 part2 的 Removed 段覆盖);v2.3.5-part2 立规则 16 第 4 次改造把 5 层降级链简化为 3 层。

---

## [v2.3.5-part1.2] - 2026-04-29 (hotfix - 硅基流动思考型 timeout 独立)

**定位**:v2.3.4-hotfix3 用 `_is_thinking_model` 模式匹配修了"识别"漏判(BUG#1 — 硅基模型不再误走 120s timeout),但**所有思考型仍套用 r1_timeout=300s 这个策略假设没核对产品现实**。老唐 0429 喂料实测第 5/11 段(1034 字)R1 截断后 L1 Kimi-K2.6 整段重提 3 次超时全失败(`Exception: API调用失败(重试3次): timeout`),但硅基流动后台费用明细显示 Kimi-K2 调用确实发生(`B202604282...` 计费记录,服务端在生成,客户端先读超时),L2 R1 镜像兜底救回 9 条完整。诊断:硅基流动 Kimi-K2.6 思考型(256K 上下文 + 思考链 + 8192 输出)实测响应 5-15 分钟,300s 是临界值触发概率高。

涉及 1 代码 + 4 项目文件(deepseek_client.py + 00 + 01 + README + CHANGELOG)。Phase 1-3 单对话完成。立规则 9 第 20 次应验。

### Fixed

- **deepseek_client.py:91-113 `__init__`**:新增 `self.siliconflow_thinking_timeout = int(os.getenv("SILICONFLOW_THINKING_TIMEOUT", "1200"))`,默认 1200 秒(20 分钟),老唐可在 .env 或环境变量设 `SILICONFLOW_THINKING_TIMEOUT=1500` 覆盖
- **deepseek_client.py:208-220 `_request` timeout 选择重写**:从"仅看模型 → 二档分支(r1_timeout / timeout)"升级为"看 endpoint + 模型 → 三档分支":siliconflow+thinking → 1200s,仅 thinking → 300s,其他 → 120s。零破坏老调用方

### Changed

- **顶部 docstring 版本号**:v2.3.4-hotfix3 → v2.3.5-part1.2,追加变更说明 T1+T2 段落(根因 / 修法 / 立规则 9 第 20 次应验)

### Migration

- **零 schema 变更,零 .env 必改**(默认 1200s 覆盖 99% 场景)
- **只替换 1 个 .py 文件**:`scripts/deepseek_client.py`
- **验证步骤**:启动后台 → 喂料历史触发截断的长文件 → 观察 L1 Kimi 不再 timeout(最长等 1200s = 20 分钟)
- **回滚方案**:恢复 v2.3.4-hotfix3 的 deepseek_client.py

### 立规则应验

- **立规则 9 第 20 次应验**:**hotfix3 修了"识别"但没修"策略"**。`_is_thinking_model` 把硅基思考型正确识别并走 r1_timeout=300s,但所有思考型套用同一 300s 这个**策略假设**没核对产品现实。**立规则升级**:对外部 SaaS 调用,timeout 必须按 endpoint 独立调优,不假设"同类模型同 timeout"。性能基准在不同厂商基础设施下差距可达 5-10 倍

---

## [v2.3.5-part1.1] - 2026-04-28 (hotfix - part1 改造遗漏:extractor 内 duplicate_checker 调用方迁移)

**定位**:v2.3.5-part1 的"replace duplicate_checker by relation_analyzer"改造时,api_server.py 完整迁移了所有调用方,但 **extractor.py 内 3 处引用未同步**(import / 实例化 / 调用)。老唐 0428 部署 v2.3.5-part1 + v2.3.4-hotfix3 后触发提取就 `ModuleNotFoundError: No module named 'scripts.duplicate_checker'` 暴露。

立规则 9 第 19 次应验(同根第 17 次 hotfix1 漏扩 R1_MODELS 集合,同根第 14 次 R1 max_tokens 默认 4K):**改造模块时未 grep 全 codebase 同步替换调用方**。立规则 50 同步应验:交付前应跑一次 `python -c "import scripts.extractor"` 拉通验证,可秒级发现 import 死链。

涉及 1 代码 + 4 项目文件。RelationAnalyzer 接口 drop-in 兼容(签名 + 返回值与 DuplicateChecker 完全一致),修复极简:仅类名/变量名替换 + 控制台文案对齐。

### Fixed

- **extractor.py 第 87 行 import**:`from scripts.duplicate_checker import DuplicateChecker` → `from scripts.relation_analyzer import RelationAnalyzer`
- **extractor.py 第 152 行 实例化**:`self.duplicate_checker = DuplicateChecker(...)` → `self.relation_analyzer = RelationAnalyzer(...)`
- **extractor.py 第 2234 行 Step 8 调用**:`self.duplicate_checker.scan_incremental(new_ids)` → `self.relation_analyzer.scan_incremental(new_ids)`

### Changed

- **变量名 + 控制台消息对齐 v2.3.5-part1 升级精神**(产品决策):
  - Step 名:`Step 8/8 重复检测` → `Step 8/8 关系分析`
  - 局部变量:`dup_count` → `rel_count`
  - 入库 message:`[发现{N}组疑似重复]` → `[发现{N}组疑似关系]`
  - 异常 print:`重复检测出错` → `关系分析出错`
- 让老唐看仪表盘时直观知道走的是六态新引擎,不是把新结果包装成"重复"

### Migration

- **零 schema 变更,零 .env 变更,零依赖变更**(RelationAnalyzer 在 v2.3.5-part1 已部署到位)
- **只替换 1 个 .py 文件**:`scripts/extractor.py`
- **验证步骤**:
  1. 启动后台,看启动日志无 `ModuleNotFoundError` 报错
  2. 强制重处理任一文件,完成后看 process_message 末尾文案是 `[发现{N}组疑似关系]`(不再是"重复")
  3. 后台日志看 `[关系分析] 增量扫描 N 条新知识点...`(relation_analyzer 内部 print)而非 `重复检测...`
- **回滚方案**:如果 RelationAnalyzer 在线上有问题,恢复 v2.3.4-hotfix3 的 extractor.py + duplicate_checker.py(假设老唐 git stash 还在)

### 立规则应验

- **立规则 9 第 19 次应验**:v2.3.5-part1 改造模块时未 grep 全 codebase 同步替换调用方。同根第 14/15/16/17/18 次,**写代码改造靠"主调用方迁移完了"凭感觉就推上线,没核对所有引用点是 bug 温床**。立规则升级:**替换 / 删除模块时,必须 grep 三连 — 旧模块名 / 旧类名 / self.旧成员名,全 scripts/ 扫,列出所有调用方一次性同步**
- **立规则 50 第 N 次应用扩**:第 7 项"改完拉通验证"应包含"模拟 import 验证"步骤。本次 hotfix3 交付时若跑了 `python -c "import scripts.extractor"` 即可秒级发现 — Claude 当时只跑了 `py_compile`(只查语法不查 import 解析),错过了暴露机会。立规则 50 第 7 项明确加上 import 验证

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
