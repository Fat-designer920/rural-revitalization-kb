# CHANGELOG

> 乡村振兴知识库搭建助手 — 版本变更记录
> 格式:版本号 — 日期 — 定位 / 新增 / 修复 / 变更 / 数据库变更

---

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
