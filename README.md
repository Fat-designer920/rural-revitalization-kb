# 乡村振兴知识库搭建助手

> 基于 DeepSeek R1/V3 双模型的专业知识库构建工具，面向四川乡村振兴领域。
>
> **知识工厂：原料 → 加工 → 质检 → 产品 → 卖钱。底座是知识库，上面长出多种产品形态。**
>
> **当前版本：v2.3.0-part2.2（F048 体检防护层 hotfix,三对话拆分完成;在 v2.3.0-part2 正式版基础上修复四类系统性 bug + 启动就绪性自检防护墙）**

---

## 系统定位

这不是一个普通的文档管理工具，而是一个**知识工厂**——将行业文件、政策法规和 20 年实战经验加工成可变现的知识产品。

**核心竞争力：** 每一条知识点都有入库质检、人工审核、政策验证、定期保鲜的完整质量链。**500 条精品级知识 > 5000 条草稿级内容**，老唐的加工（判断/注解/验证）才是付费点。

| 阶段 | 做什么 | 验证什么 |
|------|--------|---------|
| 当前 | 自用知识库做咨询，边用边喂料加注解 | 效率提升 |
| v2.3.2 后 | 本地问答助手自用 + 分享朋友试用 | 回答质量 / 体验 / 付费意愿 |
| 200 条精品+ | 写政策解读文章发行业圈子 | 内容付费意愿 |
| 300 条精品+ | 云端问答助手产品化 | C 端订阅 |
| 500 条精品+ | 投标辅助 / 培训 / 合规自检 | B 端高客单价 |

---

## v2.3.0-part2.2 本次交付内容（F048 体检防护层 hotfix）

v2.3.0-part2.2 是 **F048 知识库体检 Agent 的 hotfix**,修复上一轮老唐实测截图总分 47.16 分暴露的四类系统性 bug + 加启动就绪性自检防护墙,让六维度体检从"假绿色"走向"真能跑"。分 3 个对话交付,全部完成:

| 对话 | 范围 | 状态 |
|------|------|------|
| A 基础层 | prompt_templates.py 落地 6 个 F048 Prompt 正式版文本 + PROMPT_VERSION 升 v2.3.0-part2.2 + 补登 QC_CHECK_SINGLE;health_checker.py import 顶层化 + 6 处 Prompt key 修正(`['system']`→`['system_prompt']`/`['user']`→`['user_prompt_template']`)+ 6 处防御分支清理;03_Prompt手册.md | ✅ 2026-04-22 |
| B 防护层 | db_manager.py 三查询追加 `LEFT JOIN categories c ON c.id = kp.final_category_id` + `AS category / subcategory`;api_server.py 新增 `_health_readiness_check()` 4 层自检(Prompt import / dict 非空 / key 齐全 / db 字段契约)+ `/start` 路由前置调用(失败 400 + details,不占 _task 单例);check_system.py 第 17 项 F048 就绪度;db_health_check.py [11/11] F048 代码层契约一致性;setup.py 核心文件校验清单追加;01_工程手册.md 踩坑 6 条 + 立规则 4 条 + 对话 A/B 复盘专节 | ✅ 2026-04-22 |
| C 收尾 | health_checker.py `_dim2_structure_score` detail 追加 `uncategorized_count` / `uncategorized_pct` 可观察性字段;00_项目全景.md / README.md / CHANGELOG.md 合并 A/B 草稿为正式 `[v2.3.0-part2.2]` 条目 | ✅ 2026-04-22 |

### 四类系统性 bug 修复概览

上一轮实测截图六维度分数分布:

| 维度 | 分数 | 真假 | 根因 |
|------|------|------|------|
| ①健康 | 40.13 | 真 | 不依赖 Prompt / 分类字段 |
| ②结构 | 0 | **字段读取 bug** | db 只 AS 出 `category_id`(int),代码读 `category`(str) |
| ③加工 | 35.65 | 真 | 不依赖 Prompt / 分类字段 |
| ④关联 | 100 | **假满分** | Prompt=None → 防御分支直接返回 100 |
| ⑤打磨 | 100 | **假满分** | 同上 |
| ⑥变现 | 0 | **Prompt 未落地 + 字段读取 bug** | Prompt 从未定义 + 读不到 category |

审计 + 实测挖出四类 bug:

1. **缺陷 1 Prompt 未落地**(对话 A 修复):`prompt_templates.py` 6 个 F048 Prompt 从未定义,PROMPT_VERSION 停留 v2.2.3 → 全部落地,PROMPT_VERSION 升 v2.3.0-part2.2
2. **缺陷 2 import 静默降级**(对话 A 修复):`health_checker.py` 用 `try/except: X = None` 吞掉 ImportError → 顶层 import,失败让解释器启动时直接崩
3. **缺陷 3 字段读取 bug**(对话 B 修复):代码读 `k.get('category')` 但 db 只 AS 出 `category_id` 外键 → 三查询追加 LEFT JOIN categories + AS 字符串字段
4. **缺陷 4 Prompt key 错配**(对话 A 实测挖出):6 处 AI 调用用 `['system']`/`['user']`,实际 key 是 `system_prompt`/`user_prompt_template`。之前被缺陷 2 掩盖(None 防御分支拦在 KeyError 之前),单改 import 不修 key 六维度必立即全炸 → 6 处全改

### 启动就绪性自检防护墙(对话 B 新增)

`api_server.py /api/tools/health/start` 路由在 `with _task_lock:` **之前**调用 `_health_readiness_check()`,4 层自检:

| 层 | 检查 | 失败表现 |
|---|------|---------|
| [1] | `scripts.prompts.prompt_templates` 模块可 import | HTTP 400 + `details` 故障清单 |
| [2] | 6 个 `HEALTH_*_PROMPT` 非 None 且为 dict | 同上 |
| [3] | 每 Prompt dict 含非空 `system_prompt` + `user_prompt_template` | 同上 |
| [4] | `db.get_kp_for_health_scan()` 首条含 `category` + `subcategory` key(空库跳过) | 同上 |

**效果**:依赖不全时点"体检"按钮秒回 400 + 故障清单,不占用任务锁,可立即重试。

### 新增可观察性字段(对话 C 落地)

`health_checker.py _dim2_structure_score` 的 detail 追加:
- `uncategorized_count`:未分类 kp 数(`final_category_id IS NULL`)
- `uncategorized_pct`:未分类占比

老唐看报告时维度②结构分低,可直接判断是"数据未分类"(`uncategorized_pct > 0`)还是"分类覆盖不全"(两者都是 0 但 l1_rate/l2_rate 低)。

### 老唐需要做的操作(4 步)

v2.3.0-part2.2 **无数据库 schema 变更**,不需要重跑 migrate。

1. **备份数据库**:`启动后台.bat` 点"一键备份",或手动复制 `data/database/knowledge_base.db`。
2. **替换代码文件**:
   - 对话 A(已替换):`scripts/prompts/prompt_templates.py` / `scripts/health_checker.py`
   - 对话 B(已替换):`scripts/db_manager.py` / `scripts/api_server.py` / `scripts/check_system.py` / `scripts/db_health_check.py` / `scripts/setup.py`
   - 对话 C(本次):`scripts/health_checker.py`(detail 两字段微调) + 4 个项目文件
3. **重启服务**:关闭 `启动后台.bat` 后重开。
4. **验证**:
   - 跑 `python scripts/db_health_check.py` → [11/11] F048 代码层契约一致性全 OK
   - 跑 `python scripts/check_system.py` → 第 17 项 F048 就绪度全 OK
   - 手工体检(30 条档位):维度②结构有真实分数、维度⑥变现有分数条、六维度不崩

### 验证清单

- `db_health_check.py` [11.3] PROMPT_VERSION 显示 `v2.3.0-part2.2` → 对话 A Prompt 已落地。
- `db_health_check.py` [11.5] `OK category / subcategory 字段均存在` → 对话 B db_manager 契约已兑现。
- 体检报告维度②结构卡展开 detail 能看到 `uncategorized_count` / `uncategorized_pct` → 对话 C 落地。
- 故意破坏 prompt_templates.py 让 Prompt=None → 点"体检"按钮秒回 400 + details 故障清单 → 自检防护墙工作。
- 正常体检 30 条:维度②结构分 ≠ 0、维度⑥变现分 ≠ 0、维度④关联 ≠ 假 100、维度⑤打磨 ≠ 假 100。

---

## v2.3.0-part2 正式版历史交付

v2.3.0-part2 是 **F048 知识库体检 Agent** 的完整落地,提供"六维度扫描 + 三层打磨降级链 + 逐条 Review UI"的质量抓手闭环。分 3 个对话交付,全部完成:

| 对话 | 范围 | 状态 |
|------|------|------|
| 1/3 基础层 | prompt_templates (+6 Prompt) / migrate_v230_part2 (新建,建 2 表 3 索引) / db_manager (+12 方法) | ✅ alpha1(2026-04-20) |
| 2/3 引擎层 | health_checker.py (新建,~1350 行,六维度扫描 + 三层打磨降级链) | ✅ alpha2(2026-04-21) |
| 3/3 界面层 | api_server (+8 F048 路由 + 3 辅助函数) / review.html (工具箱第 10 卡 + 3 模态框 + 13 JS 函数) / 项目文件 00/01/03 + README + CHANGELOG 收尾 | ✅ 正式版(2026-04-22) |

### 新增能力概览

- **F048 知识库体检 Agent(完整版)**
  - 工具箱新增第 10 张紫色"知识库体检"卡,点击弹档位选择对话框(30/50/100/200/不限),每档显示预计时间
  - 六维度扫描:健康度 / 结构分布 / 加工深度 / 关联密度 / 低分打磨 / 变现匹配度(权重 25/10/20/10/20/15)
  - 三层打磨降级链:L1 主链(V3 诊断 → R1 创造打磨 → V3 校验)→ L2 保守打磨(V3 微调不创造)→ L3 人工兜底(规则标记 status=manual_review_needed)
  - 报告详情页:顶部总分 + 2×3 六维度卡 + 变现场景行(5 场景横排分数条) + "对比上次"文字 + "开始 Review"按钮
  - 逐条 Review UI:左右对比(原文 vs 打磨稿) + 诊断折叠 + tier 三色徽章(L1 绿 / L2 黄 / L3 灰) + 按 suggestion_type 动态渲染按钮
  - 采纳原子三步:operation_hook("health_adopt") 强制备份 → update_knowledge_point 字段智能映射 → apply_polish_suggestion 标记 applied,任一失败 500 附 step 标识
  - split 场景只采纳第 1 条,带 split_note 提示老唐手动处理其余;drop 场景走独立路由调 ignore_knowledge_point;略过纯前端跳转(不发请求)
  - 体检完成弹 confirm"总分 XX,是否立即查看报告?",确认后直接打开最新报告

- **F060 备份触发点补齐**:operation_hook("health_adopt") 作为第 6 个触发点正式接入(至此 6 触发点全齐:reextract / dup_merge / dup_merge_batch / full_rescan / batch_rerun / health_adopt),每类 op_name 保留最近 5 个 + 2GB 总量上限

---

## 历史版本功能累积（v2.2.3 / v2.3.0-part1 已交付）

以下能力在 v2.2.3 hotfix 落地后持续生效，v2.3.0-part1 继续沿用：

- **F057 R1 截断自动补救**：R1 输出 JSON 被截断时不再丢数据。保留已解析部分，用末条 excerpt 定位切分点，重提尾段（最多 3 次降级至 500 字），按 title + excerpt 去重合并。
- **F058 V3 质检三级降级**：每条知识点强制标 qa_score + qa_source，格式 / 超时 / 限流时三级自动降级（AI → 启发式 → 规则兜底），规则兜底条目 Tab 1 黄色高亮 + "规则兜底"标签。
- **F060 操作备份护栏**：关键操作触发点（reextract / dup_merge / dup_merge_batch / full_rescan / batch_rerun / health_adopt 6 类）先 `operation_hook(op_name)` 备份，失败立即终止；每类 op_name 保留最近 5 个 + 2GB 总量上限，pytest 全绿。
- **F061 质检补跑**：Tab 2 系统管理页"工具箱"新增"质检补跑"按钮，扫描所有 qa_score = 0 的条目触发 V3 复检，跟 F058 走同一条三级降级链。
- **F049 仪表盘工具箱优化**：Card 12/13/14 标签分布 Top5 + 展开全部 + 穿透跳转 Tab 1 带 layer1_tag 参数；工具箱"全库重复检测 + 清理并重扫"合并为"智能重复检测"三选一弹窗（最近 7 天 / 全库扫描 / 彻底重扫）。
- **F059 批量重跑 + AI 去重联动**：提取管理页"批量重跑"卡，勾选文件 → 自动备份 → 版本重提取 → 跨文件 AI 去重联动；注解警告复用 v2.2.3 机制。

---

## 模块状态速览

| 模块 | 状态 |
|------|------|
| 1 知识提取引擎 | ✅ v2.3.0-part1 完成 |
| 2 知识审核与管理 | ✅ v2.3.0-part1 完成 |
| 3 经验录入 | ✅ v2.2.0 完成 |
| 4 质量体检 | ✅ **v2.3.0-part2 完成(三对话闭环:基础+引擎+界面)+ v2.3.0-part2.2 hotfix 修复四类系统性 bug + 启动就绪性自检防护墙** |
| 5 端到端测试 | 🚧 v2.3.0 Part3 规划中 |
| 6 本地问答助手 | 🚧 v2.3.2 规划中 |
| 7 内容生产引擎 | 未开发（v2.4.0+） |
| 8 云端问答产品 | 未开发（v3.x） |
| 9 内容分发与付费 | 未开发（v3.x） |
| 10 信息采集 | 未开发（远期） |

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 运行环境 | Windows + Python 3.8+（便携版，绿色免安装） |
| AI 引擎 | DeepSeek API（R1 提取 + 低分打磨；V3 辅助判断 + 校验） |
| OCR 引擎 | 硅基流动 API（Qwen2.5-VL-72B 视觉模型） |
| 数据库 | SQLite（18 张表，v2.3.0-part2.1 起由 db_manager.init_tables() 一次建成；scripts/migrate_*.py 迁移脚本全部退役删除） |
| Web 界面 | Flask 本地管理后台（ES5 前端，无 emoji） |
| PDF 渲染 | pymupdf |
| 操作方式 | 管理后台为主，bat 入口辅助 |

---

## 双 API 架构

| API | 用途 | 模型 | 费用 |
|-----|------|------|------|
| DeepSeek | 知识提取(R1)、低分打磨创造(R1)、分类 / 质检 / 预分析 / 政策扫描 / 重复判断 / 经验速记结构化 / 体检分析 / 打磨校验 / 问答生成(V3) | deepseek-reasoner / deepseek-chat | R1 约 4 元/百万 token，V3 约 1 元/百万 token |
| 硅基流动 | 扫描件 PDF 和图片的 OCR 识别（仅 OCR，不做推理） | Qwen/Qwen2.5-VL-72B-Instruct | 约 4 元/百万 token |

**协作模式**：R1 创造 → V3 校验。硅基流动翻译（图 → 文）→ DeepSeek 理解（文 → 知识点 / 问答）。

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
3. Tab 2 系统管理 → 提取管理：
   - 文件预处理（智能重命名 + 分类建议 + .md 缓存）
   - 知识提取（R1 提取 + V3 质检三级降级 + 增量重复检测）
   - 批量重跑（v2.3.0-part1 新增，勾选文件批量版本重提 + 自动备份 + AI 去重联动）
4. Tab 1 知识审核：
   - 人工审核（逐条确认 / 编辑 / 删除）
   - 专家注解（同意 / 不同意 / 补充 / 纠错 / 经验）
   - 一级标签筛选（v2.3.0-part1 新增，从仪表盘标签卡穿透跳转）
5. Tab 2 系统管理 → 经验速记：
   - 随时记录碎片化经验，V3 自动结构化入库
```

### 3. 定期体检（v2.3.0-part2 正式版 / v2.3.0-part2.2 防护墙加固）

```
1. Tab 2 系统管理 → 工具箱 → 知识库体检
2. 弹窗选档位（30/50/100/200/不限,首次试水选 30 条约 10 分钟）
3. 体检运行中,一键提取按钮禁用 + 进度条标题"知识库体检进行中"
4. 完成弹 confirm"总分 XX,是否立即查看报告?"
5. 报告详情:2×3 六维度卡 + 变现场景 5 项分数条 + "开始 Review"按钮
6. 逐条 Review:左右对比 + L1/L2/L3 tier 徽章 + diagnosis 折叠
7. 四态操作:采纳(走备份) / 驳回(AI 建议作废) / 略过(不决策) / 确认删除(drop 场景)
```

---

## 三层标签体系（v2.3.0-part1 起在仪表盘展示）

- **第一层 业务领域**：策略落地 / 一线操作 / 政策制度 / 数据与测算 / 多维判断
- **第二层 知识形态**：概念 / 流程 / 方法论 / 清单 / 数据 / 案例 / 模板 / 经验
- **第三层 关键词**：AI 自由提取 5-15 个

---

## 迭代路线

| 版本 | 定位 | 核心功能 | 状态 |
|------|------|---------|------|
| v1.0 ~ v2.2.2 | 基础 → 提取 → 管理 → 资产沉淀 → 质量管控 | 全部已完成 | ✅ 已完成 |
| v2.2.3 hotfix | 紧急 bug 修复 + 护栏 | F057 截断补救 + F058 质检降级 + F060 操作备份 + F061 质检补跑 | ✅ 已完成 |
| v2.3.0-part1 | 工具箱整体优化 | F049 仪表盘工具箱优化 + F059 批量重跑与 AI 去重联动 + Step 8 bug 修正 | ✅ 已完成 |
| v2.3.0-part2 | 质量抓手 | F048 知识库体检 Agent(六维度扫描 + 三层打磨降级链 + 逐条 Review UI) | ✅ 已完成 |
| v2.3.0-part2.1 | schema 整合 hotfix | db_manager.init_tables() 吸收 health_reports / polish_suggestions 两表 + 3 索引；setup.py 版本号升至 v2.3.0-part2.1；删除 migrate_v223.py 和 migrate_v230_part2.py | ✅ 已交付（2026-04-22） |
| **v2.3.0-part2.2** | **F048 防护层 hotfix(三对话拆分)** | **对话 A 修四类系统性 bug(Prompt 未落地/import 静默降级/字段读取/Prompt key 错配);对话 B 加启动就绪性自检防护墙 + db 字段契约兑现 + 数据层只读契约体检;对话 C 补 uncategorized 可观察性 + 项目文件收尾** | ✅ **本次完成（2026-04-22）** |
| v2.3.0 Part3 | 端到端测试 | F062 端到端健康测试 Agent（方案 A） | 规划中 |
| v2.3.1 | 批量重算成熟度 + 关联体系 | 批量重算 content_readiness 按钮(与 F048 打磨解耦) + F020 冲突检测 + F030 知识关联网络 | 规划中 |
| v2.3.2 | 本地问答助手 | F055 顾问式答疑 + F056 发布 JSON 标准 | 规划中 |
| v2.4.0+ | 按需再议 | 内容生产 / 采集监控等 | 远期 |
| v3.x | 产品化 | 云端问答 → 培训 → 投标 | 远期 |

---

## 协作流程

### 五阶段迭代工作流

1. **需求提交** → 老唐描述问题。
2. **影响范围评估** → Claude 给修改逻辑 + 决策建议（需要老唐决策时列推荐 + 理由，不让老唐做技术判断）。
3. **代码交付** → 完整文件 + 项目文件全量更新 + 操作清单。
4. **用户执行** → 备份 → 替换 → 推送 → 更新 Projects → 验证。
5. **回滚** → 有问题新开对话。

### 技术文档（Claude Projects 4 个项目文件）

- `00_项目全景.md`：模块状态 / 迭代路线 / 商业化路径
- `01_工程手册.md`：代码文件清单 / 技术踩坑 / 关键设计决策 / **v2.3.0-part2.2 对话 A/B 四类系统性 bug 复盘专节 + 5 条立规则**
- `02_知识体系.md`：五大类分类 + 三层标签
- `03_Prompt手册.md`：27 个 Prompt 模板清单(v2.3.0-part2 含 6 个 F048 体检 Prompt,v2.3.0-part2.2 落地正式版文本)

### GitHub 仓库

https://github.com/Fat-designer920/rural-revitalization-kb

---

## 关键约束（改代码时必读）

- **bat 文件**：GBK 编码 + CRLF 换行，中文 echo 必须在 chcp 65001 之前。
- **review.html**：零 emoji + 严格 ES5（Promise .then 链，禁止 async/await 和箭头函数）。
- **api_server.py**：`Response(html, mimetype="text/html; charset=utf-8")` 返回 HTML，不用 `render_template`。
- **R1 调用**：不传 temperature，不传图片，超时 300 秒，分段 ≤ 3000 字。
- **OCR**：用硅基流动不用 DeepSeek。
- **数据库**：所有删除必须手动级联 annotations。
- **v2.2.3 铁律 1**：每条知识点必须有 qa_score + qa_source，禁止"跳过"灰色地带。
- **v2.2.3 铁律 2**:6 个关键操作触发点必须先 `operation_hook(op_name)` 备份,失败立即终止(reextract / dup_merge / dup_merge_batch / full_rescan / batch_rerun / health_adopt;v2.3.0-part1 接入 batch_rerun,v2.3.0-part2 接入 health_adopt,至此 6 触发点全齐)。
- **v2.3.0-part1 约定 1**：`extract_from_file` 返回的 `kps_info` 统一用 `kp_id` 字段，跨模块引用务必对齐（Step 8 老 bug 的根因就是字段口径不一致）。
- **v2.3.0-part1 约定 2**：批量重跑默认仅清空 extracted pending 条目，保留 confirmed / ignored；注解依赖 db 层 `delete_extracted_kps_by_source_file` 合约（只删 pending，不触 annotations）。
- **v2.3.0-part2 约定 1**:`db.apply_polish_suggestion` 只改 status,不触 knowledge_points;采纳三步(operation_hook("health_adopt") → update_knowledge_point → apply_polish_suggestion)由 api_server 层显式串起,与 v2.2.3 F061 `_qc_rerun_core` 风格一致,任一失败 500 + step 标识,不做 rollback。
- **v2.3.0-part2 约定 2**:低分候选严格口径 `(qa_score>0 AND qa_score<=2) OR qa_source='rule_fallback'`;qa_score>0 过滤未质检 kp(默认值 0.0),避免把"未质检"的 kp 误拉进打磨池。未质检应先走 F061 质检补跑补 qa_score。
- **v2.3.0-part2 约定 3**:split 场景只采纳第 1 条不自动建新 kp(避免污染审核池,老唐手动到 Tab 1 创建其余);drop 走独立 `/api/tools/health/suggestions/<sid>/drop` 路由调 `ignore_knowledge_point`,不走 `/adopt` 路由;op_name 复用 `"health_adopt"` 不新增(backup 分桶按 op_name 不碎)。
- **v2.3.0-part2 约定 4**:采纳后 `content_readiness` 保留原值不动(打磨是"修字句/补结构"不是"重评成熟度",避免 L2 保守打磨虚高成熟度统计);成熟度重算规划 v2.3.1 单开"批量重算成熟度"按钮解耦。
- **v2.3.0-part2.1 约定**:schema 单一来源原则 — `init_tables()` 必须是唯一的建表真相,任何 schema 变更都要同步改 init_tables();migrate 脚本仅作为"已部署老库的一次性升级工具",升完立即退役(源文件删除 + setup.py 吸收)。
- **v2.3.0-part2.2 约定 1**(对话 A 立):禁止"包级静默降级"— 业务必需模块的对外接口对象(Prompt/DB connection/Client)禁止使用 `try: from X import Y except: Y = None` 的兜底模式。识别信号:对象名字是"配置/实例/客户端"而不是"扩展插件"的,都应顶层 import,失败让解释器启动时直接崩。
- **v2.3.0-part2.2 约定 2**(对话 B 立):文档契约字段名必须从 schema 源文件取真相 — 所有项目文件(00/01/02/03)引用表字段名时,必须从 `db_manager.py init_tables()` 的 CREATE TABLE SQL 复制真实列名,不能靠记忆或 docstring 口述(对话 A/B 曾把 `final_category_id` 误写成 `category_id`)。
- **v2.3.0-part2.2 约定 3**(对话 B 立):长任务启动就绪性自检必须在 `_task_lock` 之前 — 所有占用 `_task` 单例的长任务 `/start` 路由前置校验都要在 `with _task_lock:` 之前执行;自检失败零污染 _task 状态,返回 400 后下次请求可立即重试。自检至少覆盖"外部依赖能 import + 依赖对象非空 + 依赖 key 齐全 + db 字段契约兑现"四类。
- **v2.3.0-part2.2 约定 4**(对话 A/B 立):项目文件契约与代码实装对齐窗口 — 项目文件"字段名承诺/API 承诺/Prompt 承诺"必须在当对话或紧邻对话内兑现到代码,不能跨版本拖延(本地化交付 + 分对话拆分时尤其容易踩坑)。

---

## 变更日志

详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 许可证与支持

本项目为个人实战资产沉淀工具，当前阶段仅供老唐本人使用。未来商业化路径见 `00_项目全景.md`。

## v2.3.0-part2.2 致谢

感谢老唐 20 年乡村振兴实战经验沉淀出的判断力,也感谢老唐上一轮在截图 47.16 分那里停住,不把"假绿色"当成"真能跑"。v2.2.3 补上了质量护栏,v2.3.0-part1 把工具箱和仪表盘往前推了一步,v2.3.0-part2 把 F048 体检抓手搭起来,v2.3.0-part2.2 则把这个抓手的四类系统性缺陷一次清掉 —— Prompt 没写的补上,静默降级的改成顶层 import,字段读错的改成 LEFT JOIN,key 错配的逐字改对。再加上一堵启动就绪性自检的墙,把所有"依赖缺失的新故障"从运行时崩提前到点按钮秒回 400。质量抓手不再是"展示型 UI",而是"真能跑的生产车间"。下一步 v2.3.0 Part3 上端到端健康测试 Agent,把所有 API 路由都纳入 AI 自检范围。
