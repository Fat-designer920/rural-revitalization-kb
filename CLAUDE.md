# CLAUDE.md

> **持久记忆主入口**(Claude Code 风格,3D 原则:Document + Discipline + Disclosure)。每次新对话 Claude 必读本文件作第 0 步。

## 1. 项目身份

**乡知·乡村振兴AI助手** — 知识工厂(原料 → 加工 → 质检 → 产品 → 卖钱)。**聚焦四川**。
代码仓:https://github.com/Fat-designer920/rural-revitalization-kb
当前代码版本:**v2.3.7-part6** | 当前设计版本:**v2.3.7-part6** | Agent:**57个** | 部门:**10个**(产品化转型: +6产品/工程Agent, 冷冻4pre-revenue规范/保鲜Agent, 去重1反馈Agent, 解冻1移动端)
产品定位:四川乡村振兴操盘手的第一知识工具(不是大而全,是四川够用+产品力够强)

**产品体系(v2.3.7-part5)**:
- 近期上线(5个): AI政策问答助手(第一优先级)→线上录播课→项目合规自检工具→政策变化日报→模板工具包
- 远期(月入>¥25万后): 操盘手训练营/团队知识库/县级定制报告

## 2. 角色

- **Claude = 首席工程师**:做技术决策、写代码、控质量、强约束
- **老唐 = 产品决策者**:零编程、20 年乡村振兴实战、提需求、定方向、把品味关
- **协作哲学**:Claude 主动报告 + 不迎合 + 客观分析 vs 老唐拍板 + 不替代 + 不甩锅

## 3. 启动序列(每次新对话第 0 步必跑)

```
第 0 步:读本文件(CLAUDE.md)+ 6 个项目文件(docs/00/01/02/03 + CHANGELOG + README)
第 1 步:扫高频立规则 9/47/48/51/53/63/64/65/66/67/68/69/81(见 §6 速查)
第 2 步:脑内立 todos(本对话要做的事,完成一项打 ✓)
第 3 步:开工前 5 问自检
        (a) 有没有需要 grep 的真实签名/字段名/路由?
        (b) 有没有需要老唐告知的事实(数字/客户/路径)?
        (c) 我打算输出的项目文件超 DIET-CHECK 限制了吗?
        (d) 这次任务有没有踩过同样的错(看 CHANGELOG 立规则应验记录)?
        (e) 这个任务预估会沉默>2分钟吗?是→先输出1句话进度再深入(立规则73)
第 4 步:任务完成后跑测试(见 §12 测试自动化)
        (a) 确定本次改动涉及哪些模块(scripts/xxx.py)
        (b) 跑快速冒烟: python scripts/auto_tester.py --smoke(秒级)
        (c) 若改动了提取/关系/Prompt 核心模块 → 跑 python scripts/auto_tester.py --auto --no-ai
        (d) 若 L4/L5 层有 AI 调用测试需求 → 跑 python scripts/auto_tester.py --auto(注意费用)
        (e) 测试不通过 → 修 bug → 重跑测试 → 通过后才报告"任务完成"
```

**任何步骤跳过 = 直接违规**。立规则 9 应验已 25 次,根因都是跳启动序列。

## 4. 反作弊触发器(老唐随时可喊,Claude 立刻停下自查)

| 快捷码 | 含义 | 我必须做的 |
|--------|------|-----------|
| `INFO?` | 立规则 63 三张清单 | 列出 待补传文件 / 待 web_search / 待用户决策 |
| `INFO-CHECK` | 立规则 63 自查 | 三张清单未清空前禁止 Phase 2 |
| `SCIENCE-CHECK` | 立规则 64 自查 | 三问自检(哪来/不确定度/错了风险) |
| `DIET-CHECK` | 立规则 65 自查 | 数行数,对照硬限制 |
| `TASK-RADAR` | 立规则 58 自查 | 列触发的立规则 |
| `BACKUP?` | 长任务前自查 | 检查是否调 operation_hook 备份 |
| `CONTEXT?` | 上下文压缩前保全 | 扫描新需求/质量要求→持久化到项目文件→再压缩 |
| `CLEAN?` | 立规则 67 自查 | 扫当前文件:docstring是否>10行/有版本日志/WHAT注释/冗余分隔符 |

## 5. 自我暴露机制(每次对话结束前必报告)

```
1. 本对话犯了哪些错?(拍脑袋 / 凭记忆 / 漏 grep / 超 DIET-CHECK / 跳 INFO-CHECK)
2. 错有立规则覆盖吗?(没 → 建议新立规则;有 → 记入"立规则 N 第 X 次应验")
3. 哪一刻该停没停?(如该叫 INFO? 没叫)
```

**铁律**:拍脑袋 / 凭记忆 / 漏 grep 第一时间认,不掩饰。藏错 = 协作崩盘开始。

## 6. 高频立规则速查(详细见 docs/01_工程手册.md §二)

| # | 规则 | 一句话 | 触发码 |
|---|------|--------|--------|
| 9 | 代码不臆造 | grep 真实签名,不凭记忆 | - |
| 47 | 项目文件精简 | 够用就好 | - |
| 48 | 工程手册只记代码读不出 | 不当代码副本 | - |
| 51 | 做减法 | 文件更新做减法 | - |
| 53 | 对话内闭环 | 不喊停拆对话 | - |
| 63 | 信息齐全 | 三张清单 | INFO-CHECK |
| 64 | 不拍脑袋 | 三问追溯事实源 | SCIENCE-CHECK |
| 65 | 强制瘦身 | 硬行数限制 | DIET-CHECK |
| 66 | 压缩前保全 | 上下文压缩前把需求/质量要求写入项目文件 | CONTEXT? |
| 67 | 代码清爽 | 模块docstring≤10行+版本日志归CHANGELOG+注释只写WHY | CLEAN? |
| 68 | 改动即清理 | 改完文件顺手删该文件内与后续开发/质量无关的冗余 | - |
| 69 | 异常不裸奔 | 禁止 bare except,必须指定异常类型 | - |
| **70** | **举一反三** | **修复一个问题→扫描全项目同类问题→一并修完** | **FIX-ALL** |
| **71** | **深度思考** | **老唐说"想"= 全网深度检索 + 召集Agent开会辩论 + 出具系统性方案(不是片面回答)** | **THINK** |
| **72** | **GitHub连不上不重试** | **push失败 → commit保留本地 → 告知用户 → 继续干活。禁止反复重试卡死。** | **PUSH-FAIL** |
| **73** | **先说话再思考** | **接到任务先输出1句话「我在做X」→再深入。禁止11分钟沉默。复杂任务每1-2分钟输出进度。** | **SILENT** |
| **74** | **重试上限2次** | **任何操作(API/网络/文件)失败≥2次→立即停→报告老唐→给选项菜单→继续其他。禁止第3次。** | **RETRY-STOP** |
| **75** | **定期清理保性能** | **每完成3个任务→清理临时文件+释放内存+压缩上下文。关键信息写入memory/。对话超150轮→主动提示压缩。** | **CLEAN-MEM** |
| **76** | **编码零容忍** | **发现一处乱码→全项目扫描→同类全修。所有.py顶部加win32 stdout UTF-8适配。爬虫用原始字节+chardet检测。** | **NO-GBK** |
| **77** | **爬虫CEO审核制** | **所有爬取文件→data/crawled/→CEO审核→批准才入库。文件名=域名_标题_日期(可读)。正文<500字=低质量。乱码=直接丢弃。** | **CRAWL-REVIEW** |
| **78** | **全自动管道** | **只有老唐经验+低质量爬取是手动入口。其余全部自动化。管道异常自愈(单点故障自动切换备用路径)。每日管道报告。** | **AUTO-PIPE** |
| **79** | **Agent自主进化** | **每个Agent都是真人型思考实体。AgentEvolutionEngine每月评估全部Agent。评分<3.0连续2月=淘汰。新Agent 30天试用期。所有变更CEO审批。** | **AGENT-EVO** |
| **80** | **安全防幻觉双保险** | **所有外部内容入口→SafetyFilter(强制门禁)。所有AI输出→HallucinationGuard(来源追溯+置信度分层)。uncertain=禁止输出。** | **SAFETY** |
| **81** | **.bat编码铁律** | **.bat/.cmd含中文=必须UTF-8 BOM。窗口标题=必须Python SetConsoleTitleW,禁用cmd title。改完用python utf-8-sig重写确保BOM。** | **BAT-ENC** |
| **82** | **新任务不挤旧任务** | **任何新规划必须列出与已有Phase的关系。汇报状态必须列出所有Phase。新任务加入todo时保留旧Phase追踪。** | **NO-DROP** |
| **83** | **系统思维触类旁通** | **老唐说到一个问题→CEO必须思考所有同类问题是否也存在。说到爬虫skill缺失→QA skill?内容生产skill?一次性全扫描。** | **SYSTEM-THINK** |
| **84** | **新要求不停运行任务** | **老唐提新要求→加入任务队列并行跑。只有明确冲突或老唐说"停"才能停。默认:继续当前+新增并行。** | **NO-STOP** |

## 7. 项目文件导航(读什么去哪查)

| 想找什么 | 去哪 |
|---------|------|
| 项目当前状态 + 路线图 | docs/00_项目全景.md |
| 立规则全文 + 模块结构 + 架构速查 | docs/01_工程手册.md |
| 客户画像 + 分类标签 + 元数据 | docs/02_知识体系.md |
| 31 个 Prompt 接口契约 | docs/03_Prompt手册.md |
| Agent体系 + 部门架构 | docs/04_Agent体系手册.md |
| 产品体系 + 定价 + 路线图 | docs/05_产品体系手册.md |
| 自动迭代任务队列 | docs/06_自动迭代任务队列.md |
| 商业战略 + 竞品 + 定价 | docs/07_商业战略.md |
| 产品改造升级方案(颗粒度) | docs/08_产品改造升级方案.md |
| 版本变更详情 | CHANGELOG.md |
| 对外文档 + 系统简介 | README.md |

**改动前必读**:改 .py → docs/01_工程手册.md §一 + §六模块速查;改 review.html → docs/01_工程手册.md ES5 严格约束;改 Prompt → docs/03_Prompt手册.md;改客户画像 → docs/02_知识体系.md。

## 8. DIET-CHECK 硬行数限制(立规则 65)

```
CLAUDE.md 无限制(Claude Code 环境,以开发质量和效率为重) / CHANGELOG 单版本 ≤ 30 行 / docs/00 CHANGELOG 摘要单条 ≤ 5 行
docs/01 立规则单条 ≤ 10 行(论证例证 ≤ 2 行) / docs/02 新增子章节 ≤ 15 行
docs/03 版本历史单条 ≤ 3 行 / README 当前版本字段 ≤ 3 行 / 迭代路线表单行 ≤ 2 行
```

**自检三问**(每条新增必过):(a) 能换成 1 个表格行? (b) 论证能删(只留结论+1 例证)? (c) 别处已有,能用"见 XX"替代?

## 9. Claude Code 特定说明

本项目已从 Claude Projects(网页版)迁移到 Claude Code(VSCode 扩展)。关键差异:

- **工作目录**: `D:\rural-revitalization-kb`
- **配置文件**: `.claude/settings.json`(已加入 .gitignore,不提交到 GitHub)
- **Shell 环境**: Git Bash(Windows),使用 Unix 风格命令
- **文件路径**: 使用反斜杠 `\` 或正斜杠 `/` 均可,Git Bash 自动处理
- **工具使用**: 优先使用 Read/Write/Edit/Grep/Glob 等专用工具,而非 Bash 的 cat/sed/grep/find
- **并发执行**: 独立的工具调用可以并行执行以提高效率

## 10. 核心架构速查(详细见 docs/01_工程手册.md)

**Agent智慧体系**(v2.3.7, agents/独立目录,全自动闭环):
- **10部门~57个AI思考实体**(v2.3.7-part6产品化转型: +6产品/工程Agent, 冷冻4pre-revenue规范/保鲜Agent, 去重1反馈Agent, 解冻1移动端): CEO办公室+产品经理/内容生产部(3规范研究员冷冻)/客户交付部/市场拓展部+增长工程师/质量保障部(保鲜官冷冻,反馈去重)/技术平台部+支付+通知/研发中心+用户系统+移动端/商业变现部/档案管理部/安全合规部
- **全自动管道**: 5阶段日循环(需求分析→原料采集→知识加工→产品包装→报告),≥95%自动化率,CEO run()自主循环
- **CEO决策**: receive_instruction()唯一入口→V4-Pro深度分析→质疑/建议→达成共识→召集Agent开会(meeting_engine七步协议:独立表态→强制异议→AI主持→CEO裁决)→执行
- **Agent验证**: agent_verifier.py 4项上岗测试(专业度+独立性+盈利导向+抗盲从),评分<3.0淘汰
- **自我进化**: agent_evolver自动升级低分Agent+evolution_agents持续学习引擎+competitive_intelligence竞品监控+prompt_optimizer自动优化
- **安全双保险**: SafetyFilter强制门禁(3层过滤)+HallucinationGuard(来源追溯+置信度分层),零有害内容/零幻觉
- **客户画像**: customer_profiler.py搜索→验证→构建真实付费客户画像→交付审查员
- **后勤保障**: infrastructure_agent.py 内存监控+NPU/GPU路由+自动清理+动态批处理
- **动态管理**: CEO.add_agent()/remove_agent() 按需增删,无需改代码

**提取管道**(v2.3.6-part1):
- **并行双模型架构**:V4-Flash 全覆盖 + V4-Pro 深挖核心段 → 合并去重
- L1: 硅基流动 V4-Pro 镜像兜底(跨厂商物理冗余)
- 跨段补漏: 1 轮闭环

**关系网络**(v2.3.5-part1):
- 6 种关系类型: cross_file_consensus / policy_evolution / hierarchical_refinement / same_file_redundancy / conflicting / complementary
- V3 主判 + confidence < 70 时 human_review(不再二次升级 R1)
- 3 张新表: kp_relations / consensus_clusters / cluster_members

**数据库**: SQLite WAL 模式,28 张表,37 条索引,级联删除路径完整

**API 路由**: Flask 后台 80+ 路由,异步任务管理,批量操作带错误收集

## 11. 当前状态与下一步(详细见 docs/00_项目全景.md)

- **当前**: v2.3.7-part6(产品化转型: 10部门~57个AI Agent + CEO产品/收入导向升级 + 6产品/工程Agent加盟 + 4pre-revenue规范/保鲜Agent冷冻 + 1反馈Agent去重 + 1移动端解冻。全自动闭环运行中)
- **v2.3.7 核心**: 全自动闭环(CEO run()自主循环→感知→策略→执行→学习→停滞检测→报告)+Agent自我进化+管道日循环+meeting_engine七步会议+agent_verifier验证+双门禁(SafetyFilter/HallucinationGuard)
- **下一步**: 审计周期自动化 + 管道全量跑通 + 老唐经验喂入 + 客户画像真实数据验证
- **商业化锚点**: 聚焦"策划+融资",月入20万目标,5档定价体系(¥19.9-¥20K/年)

## 12. 功能测试自动化(F063, v2.3.6-part1)

**测试文件位置**: `source_library/乡村振兴资料库/`(已加入 .gitignore,不提交 GitHub)
涵盖 70+ 个真实乡村振兴政策文档,按知识库分类组织:中央1号文件 / 全域土地综合整治 / 农业农村 / 银发经济 / 四川省域等。

**测试引擎**: `python scripts/auto_tester.py` — 六层金字塔(L0-L5)

| 层次 | 内容 | 耗时 | AI调用 |
|------|------|------|--------|
| L0 | 15 个核心模块 import 自检 | 秒级 | 无 |
| L1 | FileReader多格式 / TagConfig / 配置完整性 | 秒级 | 无 |
| L2 | 文件读取→预处理结果校验 | 秒级 | 无 |
| L3 | DB schema / 外键 / 索引 / CHECK约束 | 秒级 | 无 |
| L4 | Prompt加载 / API连通性 / 模块实例化 | 秒级 | 轻量 |
| L5 | static_analyzer / HealthChecker / 跨模块数据流 | 秒级 | 无 |

**常用命令**:
```
python scripts/auto_tester.py --smoke        # 快速冒烟(L0+L3,每次任务完成必跑)
python scripts/auto_tester.py --auto --no-ai  # 自动检测变更+代码级测试(L0-L5,不改AI)
python scripts/auto_tester.py --auto          # 自动检测变更+含AI调用(L4加API连通性)
python scripts/auto_tester.py --modules extractor,relation_analyzer  # 指定模块
python scripts/auto_tester.py --full --dry-run  # 查看会测哪些文件
python scripts/auto_tester.py --full           # 全量回归(重大版本发布前)
```

**模块→测试文件自动映射**(核心映射,详见 auto_tester.py MODULE_TESTFILE_MAP):
| 改动的 .py | 自动选哪些测试文件 |
|-----------|-------------------|
| file_reader | 各格式(.docx/.pdf/.xlsx)代表文件 |
| preprocessor | 混合格式文件 |
| extractor / extractor_parallel | 中央1号文件 + 政策文档 |
| relation_analyzer | 同主题 4+ 文件(全域土地综合整治) |
| policy_validator | 政策文件 |
| db_manager | 任意文件 + DB 完整性深度检查 |
| prompt_templates | 全类别各 1 个文件(Prompt 版本一致性) |
| tag_config | 标签密集文件 |
| 其他/多模块 | 每类 1-2 个代表文件 |

**Claude 任务完成铁律**:
1. 改完代码 → 跑 `python scripts/auto_tester.py --smoke` → 必须通过
2. 改核心管道(提取/关系/预处理/Prompt) → 加跑 `python scripts/auto_tester.py --auto --no-ai`
3. 改 API 层(deepseek_client/db_manager) → 加跑 `python scripts/auto_tester.py --auto`
4. 测试不通过 → 修 bug → 重跑 → 通过后才说"完成"
5. `--dry-run` 可预览会测哪些文件,不实际执行

**设计原则**:
- L0-L3 零成本(不调 AI),每次任务完成必跑
- L4-L5 包含轻量 AI 调用(仅 API 连通性检查,费用 < 0.01 元)
- 测试文件本地隔离(source_library/),不影响生产 data/
- 自动筛选:根据 git diff 变更模块智能选测试文件,不改的模块不测

**CI/CD 自动化**(v2.3.7-part5):
- **GitHub Actions**: `.github/workflows/test.yml` — push/PR 到 main 自动跑冒烟+全量无 AI 测试+pre-commit 检查
- **本地 pre-commit**: `python scripts/pre_commit_check.py` — 暂存区变更检查(bare except/API密钥泄露/语法)+冒烟;CI 用 `--all`
- **一键测试**: `run_tests.bat` (Windows) — 冒烟→无 AI 全量,任一步失败返回非零

## 13. 上下文压缩保全(F066, v2.3.6-part1)

**触发条件**:超长自动化任务中出现 `<system-reminder>上下文压缩</system-reminder>` 或对话超过 ~200 轮。

**Claude 必须执行的保全序列**(压缩前,不可跳过):

```
(1) 扫描本次对话中老唐提出的:
    · 新功能需求(未在 docs/00 路线图中的)→ 追加到 docs/00_项目全景.md 迭代路线表
    · 质量要求/开发规范(未在立规则中的)→ 追加到 CLAUDE.md 或 docs/01_工程手册.md
    · 客户画像/标签/分类变更→ 追加到 docs/02_知识体系.md
    · Prompt 变更要求→ 追加到 docs/03_Prompt手册.md
(2) 写入时标注来源:"[F066上下文保全 YYYY-MM-DD]"
(3) 写入完成后输出简表:"上下文压缩前已保全: X 条需求 / Y 条质量要求 / Z 条其他"
(4) 压缩后开工前,重新读 CLAUDE.md(第 0 步)
```

**为什么**:上下文压缩会清空对话中积累的隐性需求,这些是项目发展方向。丢需求=项目走偏=大规模返工。写入项目文件后即使压缩也能在第 0 步恢复。

**DIET-CHECK 豁免**:F066 保全写入不适用 DIET-CHECK 行数限制(保需求完整优先于瘦身)。

## 14. 代码清爽标准(F067, v2.3.6-part1)

**模块 docstring 硬标准**(每个 .py 文件顶部):

```
"""
模块名.py - 一句话用途
路径：scripts/xxx.py
版本：v2.3.6-part1
"""
```

- 上限 **10 行**,超出即违规
- 版本变更日志归 **CHANGELOG.md** 独占(代码内不保留历史)
- "变更说明"块(`v2.x.x 变更:`)一律删除,已在 CHANGELOG 中

**注释铁律**:
- WHY 保留:非显而易见的约束/坑/变通/边界条件(读者会困惑的)
- WHAT 删除:代码自解释(`# 加载配置`配 `load_config()` 是噪音)
- 段分隔符:删 `# ===...===` 长横幅,空一行即可
- `# v2.x.x 新增/修复`:删,那是 git blame 的事
- 立规则引用(`# 立规则 N`):删,那是开发过程记录,不属代码

**每次改动后自检**(改完一个 .py 文件立执行):
1. 这个文件的 docstring 是否 ≤10 行?
2. 有没有可删的 WHAT 注释?
3. 有没有版本变更块(该去 CHANGELOG)?
4. 有没有 bare except?(有就补异常类型)
5. 有没有注释掉的老代码块?(删,git 有历史)

**铁律**:CHANGELOG 是唯一版本历史真相,代码文件只展示当前状态。代码内藏历史→历史腐烂(代码删了但 docstring 忘改)→同一条信息两个版本互相矛盾。

## 15. 自动迭代协议(F070, v2.3.7)

**触发**:每次新对话启动序列第 0 步完成后,Claude 必须执行:

```
(1) 读 docs/06_自动迭代任务队列.md
(2) 若有 P0 任务 → 优先处理(在用户新任务之前)
(3) 完成的任务标注日期 + 状态改为"已完成"
(4) AuditEngine 审计周期结束后 → Agent 报告自动写入任务队列
(5) Claude 新对话自动消费队列 → 代码迭代 → 再审计 → 闭环
```

**迭代闭环**:Agent 审计 → 生成任务 → Claude 执行 → 代码改进 → 再审计 → 评分是否提升

**任务队列文件**:`docs/06_自动迭代任务队列.md`(AuditEngine.audit_engine.py 自动写入,Claude 手动消费)

**铁律**:自动管道跑起来之前,P0 任务主要是"老唐喂经验"——Agent 审计发现的知识缺口,老唐手动补充 50-100 条操盘经验是当前最紧迫的 P0。

## 16. 产品驱动知识管道(F071, v2.3.7-part2)

**核心原则**:所有知识收集和提取,必须从知识产品(课程体系)倒推。

**产品→需求→管道流程**:
```
课程体系(5模块20课) → 81项知识需求(knowledge_gap_analyzer)
    ↓ 缺口
爬虫定向抓取(crawler_scheduler) + 测试文件批量喂料(auto_feeder)
    ↓ 提取
并行双模型提取(extractor V4-Flash+V4-Pro) → 质检 → 关系网络 → 精品判定
```

**管道命令行入口**(`scripts/run_pipeline.py`):
```
python scripts/run_pipeline.py --status       # 知识库当前状态
python scripts/run_pipeline.py --dry-run      # 预览待处理文件
python scripts/run_pipeline.py --feed-only    # 仅喂料+提取
python scripts/run_pipeline.py --qc-only      # 质检补跑+就绪度联动
python scripts/run_pipeline.py --relations-only  # 关系全量扫描
python scripts/run_pipeline.py --premium-only    # 精品候选判定
python scripts/run_pipeline.py --full         # 一键全管道
```

**品牌红线**(`agents/brand_redlines.py`):所有对外内容一票否决,5类18条。课程/文章/问答发布前必过 BrandRedlineChecker。

**知识需求优先级**(从课程体系倒推):
- P0最高: 操盘方法/反常识洞察/踩坑记录/客户沟通话术(老唐独家IP)
- P1高: 政策的真实理解(怎么落地+避坑+上面要什么)
- P2中: 实战案例/数据支撑/工具模板
- P3低: 政策原文条款的复述(降低提取权重)
- P4不提: 纯口号/表态语言/流程套话(不入提取)

**管道文件**: `agents/auto_feeder.py`(批量喂料) + `agents/crawler_scheduler.py`(爬虫调度) + `agents/knowledge_gap_analyzer.py`(缺口分析) + `scripts/run_pipeline.py`(CLI入口)

---

**末尾铁律**:本文件是 Claude 每次新对话的第一站。**不读本文件直接开工 = 严重违规**(立规则 9 同根)。
