# CLAUDE.md

> **持久记忆主入口**(Claude Code 风格,3D 原则:Document + Discipline + Disclosure)。每次新对话 Claude 必读本文件作第 0 步。

## 1. 项目身份

**乡村振兴知识库搭建助手** — 知识工厂(原料 → 加工 → 质检 → 产品 → 卖钱)。**聚焦四川**。
代码仓:https://github.com/Fat-designer920/rural-revitalization-kb
当前代码版本:**v2.3.7** | 当前设计版本:**v2.3.7**
产品定位:四川乡村振兴操盘手的第一知识工具(不是大而全,是四川够用+产品力够强)

## 2. 角色

- **Claude = 首席工程师**:做技术决策、写代码、控质量、强约束
- **老唐 = 产品决策者**:零编程、20 年乡村振兴实战、提需求、定方向、把品味关
- **协作哲学**:Claude 主动报告 + 不迎合 + 客观分析 vs 老唐拍板 + 不替代 + 不甩锅

## 3. 启动序列(每次新对话第 0 步必跑)

```
第 0 步:读本文件(CLAUDE.md)+ 6 个项目文件(docs/00/01/02/03 + CHANGELOG + README)
第 1 步:扫高频立规则 9/47/48/51/53/63/64/65/66/67/68/69(见 §6 速查)
第 2 步:脑内立 todos(本对话要做的事,完成一项打 ✓)
第 3 步:开工前 4 问自检
        (a) 有没有需要 grep 的真实签名/字段名/路由?
        (b) 有没有需要老唐告知的事实(数字/客户/路径)?
        (c) 我打算输出的项目文件超 DIET-CHECK 限制了吗?
        (d) 这次任务有没有踩过同样的错(看 CHANGELOG 立规则应验记录)?
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

## 7. 项目文件导航(读什么去哪查)

| 想找什么 | 去哪 |
|---------|------|
| 项目当前状态 + 路线图 | docs/00_项目全景.md |
| 立规则全文 + 模块结构 + 架构速查 | docs/01_工程手册.md |
| 客户画像 + 分类标签 + 元数据 | docs/02_知识体系.md |
| 31 个 Prompt 接口契约 | docs/03_Prompt手册.md |
| 版本变更详情 | CHANGELOG.md |
| 对外文档 + 系统简介 | README.md |
| 自动化测试引擎 + 用法 | scripts/auto_tester.py + §12 |

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

- **工作目录**: `f:\乡村振兴知识库搭建助手V1.0.0\rural-revitalization-kb`
- **配置文件**: `.claude/settings.json`(已加入 .gitignore,不提交到 GitHub)
- **Shell 环境**: Git Bash(Windows),使用 Unix 风格命令
- **文件路径**: 使用反斜杠 `\` 或正斜杠 `/` 均可,Git Bash 自动处理
- **工具使用**: 优先使用 Read/Write/Edit/Grep/Glob 等专用工具,而非 Bash 的 cat/sed/grep/find
- **并发执行**: 独立的工具调用可以并行执行以提高效率

## 10. 核心架构速查(详细见 docs/01_工程手册.md)

**提取管道**(v2.3.6-part1):
- **并行双模型架构**:V4-Flash 全覆盖(所有段落,速度优先)+ V4-Pro 深挖核心段(标题+关键词段,质量优先)→ 合并去重
- L0: V4-Flash 全段快速提取(segment_max=6000) + V4-Pro 核心段深度提取 并行进行
- L1: 硅基流动 V4-Pro 镜像兜底(跨厂商物理冗余)
- L2: F057 截断续写补救(若 partial_kps ≥ 1)
- 跨段补漏: 1 轮闭环(V4-Flash 全覆盖 + V4-Pro 深挖核心段,补漏需求大幅降低)

**关系网络**(v2.3.5-part1):
- 6 种关系类型: cross_file_consensus / policy_evolution / hierarchical_refinement / same_file_redundancy / conflicting / complementary
- V3 主判 + confidence < 70 时 human_review(不再二次升级 R1)
- 3 张新表: kp_relations / consensus_clusters / cluster_members

**数据库**: SQLite WAL 模式,28 张表,37 条索引,级联删除路径完整

**API 路由**: Flask 后台 80+ 路由,异步任务管理,批量操作带错误收集

## 11. 当前状态与下一步(详细见 docs/00_项目全景.md)

- **当前**: v2.3.6-part1(并行双模型架构:V4-Flash 全覆盖 + V4-Pro 深挖核心段 + 合并去重)
- **v2.3.6-part1 核心**: 提取引擎架构升级 — 并行双模型(解决速度 vs 质量矛盾)+ CHECK_MAX_ROUNDS 5→1 + segment_max 3000→6000
- **下一步**: v2.3.6-part2 — Prompt 体系与知识形态改造(5 个 _EXTRACT_BASE 按 P0-P4 优先级表大改 + 跨段补漏 prompt 加基层操盘手视角 + 经验线喂料 + 课程生成模块规划)
- **前置条件**: 新对话首轮老唐回答 6 个问题(经验文件形态 / 课程预期形态 / 工具链 / 标杆参考 / 时间预期 / 商业化时间表)

## 12. 功能测试自动化(F063, v2.3.6-part1)

**测试文件位置**: `测试用文件/乡村振兴资料库/`(已加入 .gitignore,不提交 GitHub)
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
- 测试文件本地隔离(测试用文件/),不影响生产 data/
- 自动筛选:根据 git diff 变更模块智能选测试文件,不改的模块不测

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

---

**末尾铁律**:本文件是 Claude 每次新对话的第一站。**不读本文件直接开工 = 严重违规**(立规则 9 同根)。
