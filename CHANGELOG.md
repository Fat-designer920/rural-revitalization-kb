# 变更日志

## v2.1.0-c 第3批 -- 提取质量加固：V3质检+审核反馈统计

发布日期：2026-03-27

变更内容：
- extractor.py新增V3质检(Step 6)：提取完成后自动对所有知识点进行5维度评分
- 质检维度：独立可用性/信息密度/颗粒度合理性/标签匹配度/重复嫌疑
- 质检结果写入qa_score(1-5分)和qa_flags(问题标记数组)
- api_server.py新增sort_by_qa参数支持，按质检分数升序排列
- api_server.py的_safe()新增qa_flags字段JSON解析
- review.html新增质检分数徽标(优/中/差三档配色)
- review.html新增质检问题标记展示(翻译为中文)
- review.html新增"质检排序"按钮(低分优先审核)
- 新增review_analytics.py审核反馈统计脚本(6维度分析+总结建议)
- 新增审核统计.bat
- 版本号统一更新至v2.1.0-c

新增文件：review_analytics.py(新增), 审核统计.bat(新增)
修改文件：extractor.py(新增V3质检), api_server.py(质检排序+版本号), review.html(质检展示+版本号)
数据库迁移：不需要（qa_score/qa_flags字段已在第2批迁移中添加）

---

## v2.1.0-c 第1-2批 -- 提取质量加固：Prompt重写+智能分段+预分析

发布日期：2026-03-27

变更内容：
- 第1批：prompt_templates.py深度重写(893行,15个Prompt)
  - 5个提取Prompt产品导向重写(颗粒度标准+正反示例+自检指令+四川标注+数据精确)
  - 4个V3辅助Prompt新增(PRE_ANALYSIS/QC_CHECK/SEGMENT_SUMMARY/CROSS_SEGMENT_CHECK)
  - 6个共享策略块+PROMPT_VERSION版本追踪
- 第2批：extractor.py重大改造(1035行)
  - V3预分析(质量预筛+分类建议,失败不降级)
  - 三级智能分段(V3结构摘要>本地规则>段落边界,绝不机械切割)
  - 上下文接力(前段知识点标题+前段末尾200字+文件结构摘要)
  - 跨段补漏检查(V3比对文件大纲与知识点标题)
  - 费用预估(大文件提取前显示)
  - prompt_version记录(每条知识点记录版本号)
  - 数据库迁移脚本(migrate_v210c.py, 6个新字段)
  - 一键提取.bat

新增文件：migrate_v210c.py, 一键提取.bat
修改文件：prompt_templates.py(重写), extractor.py(重写), db_manager.py(新字段)
数据库迁移：migrate_v210c.py(source_files+3, knowledge_points+3)

---

## v2.1.0-b -- 安全网：知识库架构升级迁移（阶段二）

发布日期：2026-03-25

变更内容：
- 新增UpgradeManager架构升级迁移管理器
- 一键扫描所有知识点,对比当前架构要求(免费,秒级)
- 规则检查:检测缺失的三层标签、元数据,自动分类(可补标签/需AI评估)
- AI补标签(V3模型,费用低):从现有内容出发,直接补充缺失的标签和元数据
- AI质量评估(V3模型):判断内容是否粗糙,区分"合格/补标签/需重提取"
- 重提取调度:删除旧知识点 → 源文件从completed/复制到processing/ → 用户运行提取
- 升级前自动备份(调用BackupManager),出问题可一键恢复
- 费用预估展示,用户确认后才执行
- db_manager新增get_all_knowledge_for_upgrade()升级检查专用查询
- 新增一键知识库升级.bat

新增文件：upgrade_manager.py(新增), 一键知识库升级.bat(新增)
修改文件：db_manager.py(新增查询方法)
数据库迁移：不需要

---

## v2.1.0-a -- 安全网：备份恢复（阶段一）

发布日期：2026-03-25

变更内容：
- 新增BackupManager备份恢复管理器
- 一键备份：SQLite原生backup API，保证数据一致性
- 一键恢复：列表选择+二次确认+恢复前自动备份
- 备份清理：超30天自动清理，至少保留3个
- 备份状态查询接口（供check_system.py集成）
- 新增一键备份.bat、一键恢复.bat

新增文件：backup_manager.py(新增), 一键备份.bat(新增), 一键恢复.bat(新增)
数据库迁移：不需要

---

## v2.0.0-c -- 变现底座：审核界面全面改版（阶段三）

发布日期：2026-03-23

变更内容：
- 审核界面全面改版：精致配色体系、卡片布局重构、标签胶囊样式、柔和阴影
- 三层标签展示：分类标签6组配色、属性标签键值对、关键词灰色胶囊
- 三层标签编辑：分组下拉选择器、维度编辑器、关键词自由输入
- 就绪度/权威度展示+编辑：卡片徽标显示，编辑弹窗可调整
- 物理删除功能：单条+批量删除，二次确认弹窗（不可恢复）
- 批量操作增强：新增批量忽略、批量删除
- 分类体系去编号：树形列表只显示名称，更干净
- 筛选增强：新增按就绪度筛选
- 搜索覆盖三层标签关键词
- 新增/api/tag-definitions接口，前端动态获取标签体系定义
- db_manager新增delete_knowledge_point()物理删除方法

受影响文件：review.html(重写), api_server.py(重大改造), db_manager.py(新增删除方法)
数据库迁移：不需要（调试阶段删库重建）
v2.0.0变现底座版全部三个阶段完成。

---

## v2.0.0-b -- 变现底座：Prompt重写+提取引擎三层标签适配（阶段二）

发布日期：2026-03-23

变更内容：
- 5个提取Prompt全部重写，输出新增三层标签+元数据
- 旧TAG_STRATEGY替换为THREE_LAYER_TAG_STRATEGY，标签清单从tag_config.py动态注入
- extractor.py解析三层标签并写入数据库新字段
- 新增_sanitize_tags()校验AI返回的标签数据
- TAG_SUGGESTION_PROMPT重写为三层标签版
- 新增QA_DERIVATION_PROMPT（待激活）
- tag_config.py新增get_metadata_for_prompt()
- 清理迁移脚本

受影响文件：prompt_templates.py(重写), extractor.py(重写), tag_config.py(微调)

---

## v2.0.0-a -- 变现底座：数据库重构+三层标签配置（阶段一）

发布日期：2026-03-23

变更内容：
- 系统定位升级为知识产品变现底座
- 三层标签体系+元数据+知识关联+使用追踪
- 数据库从9张表扩展到13张表

受影响文件：db_manager.py(重写), tag_config.py(新增)

---

## v1.1.0 -- 审核增强+分类管理+AI建议+全文搜索

发布日期：2026-03-20

变更内容：
- 树形分类筛选、全文搜索、编辑回滚+移除、忽略恢复
- 新增一级/二级分类、AI分类建议、分类概览、标签质量过滤

---

## v1.0.1 -- 提取引擎增强

发布日期：2026-03-19

变更内容：
- R1模型深度推理、5个Prompt强化、MD5去重、failed隔离

---

## v1.0.0 -- 核心版首次发布

发布日期：2026-03-18

变更内容：
- 核心工作流、10个脚本+11个bat+Flask审核界面
- SQLite 8张表+5种Prompt+API加密+费用保护+系统自检
