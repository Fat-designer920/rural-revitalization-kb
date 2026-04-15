# 变更日志

## v2.2.1 (2026-04-15) - 重复检测批量处理 + 审核体验优化

### 新增
- **重复组批量操作(F050)**: 全选/多选重复组，支持"批量按AI建议处理"和"批量标记非重复"两种模式，238组不用一个一个点了
- **重复组成员多选保留**: 每条知识点前加勾选框(AI建议的默认勾选)，支持同一组保留多条知识点
- **待审核全选全部**: 全选当前页后出现提示条，可一键选择本次筛选条件下的所有知识点(跨页)

### 修复
- **批量按钮数字不刷新**: 处理完知识点后按钮上的计数现在自动更新，不需要手动刷新页面

### API变更
- `POST /api/duplicate-groups/<gid>/resolve`: 新增`keep_ids`参数(数组)，支持保留多条；原`keep_id`(单个)向下兼容
- `POST /api/duplicate-groups/batch-resolve`: 新增接口，支持批量处理重复组
- `GET /api/knowledge-points/ids`: 新增接口，返回当前筛选条件下所有知识点ID

### 影响文件
- `scripts/api_server.py` — 3处改动(resolve改造+2个新接口)
- `web/templates/review.html` — 重复面板重构+全选增强+刷新修复

## v2.2.0 bugfix-6 -- 强制重新处理已完成文件+annotations清理修复

发布日期：2026-04-12

变更内容：
- **强制重新处理已完成文件**
  - preprocessor.py: 新增force_reprocess参数,勾选后completed文件不跳过
  - preprocessor.py: 强制重处理时先删旧知识点+注解+source_files记录+completed旧文件+.md缓存
  - preprocessor.py: 新增_clean_completed_file()方法+self.completed路径
  - api_server.py: POST /api/tasks/preprocess接受force_reprocess参数并透传
  - review.html: 提取管理区新增"强制重新处理"勾选框+灰字提示
  - review.html: startTask()读取勾选框状态传参,标题区分普通/强制模式
- **删除知识点时annotations遗漏修复**
  - db_manager.py: delete_kps_by_source_file()补上DELETE FROM annotations(修复版本重提取遗漏注解)
  - db_manager.py: delete_knowledge_point()补上DELETE FROM annotations(修复物理删除遗漏注解)

修改文件：preprocessor.py, db_manager.py, api_server.py, review.html

---


## v2.2.0 bugfix-5 -- 文档来源属性(doc_origin)

发布日期：2026-04-12

变更内容：
- **文档来源属性**
  - db_manager.py: add_source_file()新增doc_origin参数(self/external)
  - preprocessor.py: 预处理流程透传doc_origin到source_files表
  - api_server.py: POST /api/tasks/preprocess接受doc_origin参数
  - extractor.py: doc_origin='self'时强制source_nature=personal_experience+authority=firsthand
  - review.html: 提取管理区新增"文档来源"下拉框(外部文献/我的经验文档)
  - migrate_v220_bf5.py: source_files表新增doc_origin字段(默认external)

修改文件：db_manager.py, preprocessor.py, api_server.py, extractor.py, review.html
新增文件：migrate_v220_bf5.py

---

## v2.2.0 bugfix-4 -- 来源属性感知+系统性文章合并规则

发布日期：2026-04-11

变更内容：
- **来源属性感知（SOURCE_NATURE_INSTRUCTION）**
  - prompt_templates.py: 新增SOURCE_NATURE_INSTRUCTION共享策略块（6种来源类型→分类策略映射）
  - prompt_templates.py: 注入全部5个提取Prompt，位于DOCUMENT_FORM_INSTRUCTION之后
  - prompt_templates.py: PRE_ANALYSIS_PROMPT新增source_nature输出字段
  - prompt_templates.py: CONTEXT_RELAY_TEMPLATE新增source_nature传递
  - extractor.py: 从预分析结果提取source_nature，传递给R1提取上下文
  - extractor.py: _build_context_relay单段文件也传递来源属性
  - 解决：第三方调研报告被全部分成"操盘经验"的分类失准问题
- **系统性文章合并规则增强**
  - prompt_templates.py: DOCUMENT_FORM_INSTRUCTION新增3条合并规则
  - 总分合并：总述段不单独提取（信息已被分述覆盖）
  - 因果链不拆分：同一主题的原因分析+对策建议合并为一条
  - 论点去重：核心结论相同的"为什么"和"怎么做"合并保留更完整的那条
  - 解决：系统性文章17条知识点有重叠、粒度偏细的问题
- **Prompt版本升级**
  - prompt_templates.py: PROMPT_VERSION升级v2.2.3

修改文件：prompt_templates.py, extractor.py

---

## v2.2.0 bugfix-3 -- 文档形态感知+类型中文映射+摘录滚动

发布日期：2026-04-11

变更内容：
- **提取Prompt文档形态感知**
  - prompt_templates.py: 新增DOCUMENT_FORM_INSTRUCTION共享策略块(4种文档形态→颗粒度适配)
  - prompt_templates.py: 注入全部5个提取Prompt，解决编制大纲拆太碎、系统性文章论证链断裂问题
  - prompt_templates.py: SELF_CHECK_INSTRUCTION新增第6条文档形态适配检验
  - prompt_templates.py: PROMPT_VERSION升级v2.2.2
- **审核界面显示修复**
  - review.html: 新增ETN映射，experience_type从英文代码改为中文显示
  - review.html: 原文摘录展开改为max-height:360px+滚动条方案

修改文件：prompt_templates.py, review.html

---

## v2.2.0 bugfix-2 -- 仪表盘数据修复+审核界面UI优化

发布日期：2026-04-11

变更内容：
- **仪表盘数据修复**
  - api_server.py: dashboard端点全部改为直接SQL查询,不依赖get_statistics()
  - api_server.py: total_kp直接GROUP BY求和(修复显示0的bug)
  - api_server.py: by_type统计全部知识点(修复只统计confirmed的bug)
  - api_server.py: qa_distribution用CAST(qa_score AS INTEGER)(修复浮点数key不匹配导致全0)
  - api_server.py: freshness新增managed字段(已设保鲜周期的知识点数)
  - api_server.py: manual_kps查询条件修正为experience_note(原来用manual查不到)
- **审核界面UI优化**
  - review.html: 原文摘录区支持展开/收起(内容超120px显示展开全文按钮)
  - review.html: 分页按钮padding自适应(修复"下一页"按钮畸形)
  - review.html: API费用卡片精简(移除分类明细,只保留总额+上限+7天趋势)
  - review.html: 保鲜卡片新增"已设保鲜周期"计数
  - review.html: Tab2切换时自动检测运行中任务并恢复进度显示

修改文件：api_server.py, review.html

---

## v2.2.0 bugfix -- 扫描件PDF OCR + 预处理markdown缓存 + API费用UI增强

发布日期：2026-04-11

变更内容：
- **扫描件PDF OCR修复（硅基流动API）**
  - deepseek_client.py: ocr_image()改用硅基流动Qwen2.5-VL-72B视觉模型
  - deepseek_client.py: 新增_ocr_pdf()用pymupdf逐页渲染后OCR
  - deepseek_client.py: 新增_ocr_single_image()调用硅基流动API
  - deepseek_client.py: 新增_get_siliconflow_api_key()读取硅基API Key
  - config_wizard.py: 新增第4项硅基流动API Key配置+测试按钮
  - 新增依赖: pymupdf
- **预处理markdown缓存（消除双重OCR）**
  - preprocessor.py: 预处理后将内容保存为.md缓存文件到processing目录
  - extractor.py: 优先读取.md伴侣缓存文件,无缓存时才读原文件
  - extractor.py: _move_to_completed/_move_to_failed同步移动.md伴侣文件
  - api_server.py: 文件管线计数排除.md伴侣文件
- **预处理智能hash去重修复**
  - preprocessor.py: completed状态才跳过;processing/failed状态检查物理文件是否存在
  - preprocessor.py: 物理文件已不存在时清理旧DB记录,允许重新处理
- **任务完成undefined显示修复**
  - api_server.py: 预处理结果新增skip字段
  - review.html: skip/total_kps安全处理,不再显示undefined
- **API费用数据统一+可视化增强**
  - api_server.py: 仪表盘API费用改为直接从api_call_logs查询(与详情弹窗一致)
  - api_server.py: 仪表盘新增api_today_detail/api_trend_7d/daily_limit字段
  - review.html: API费用卡片增强(上限显示+今日分类明细+7天趋势柱状图)

修改文件：deepseek_client.py, preprocessor.py, extractor.py, api_server.py, review.html, config_wizard.py

---

## v2.2.0 第1批 -- 专家注解+经验速记：F029+F045

发布日期：2026-04-09

变更内容：
- **F029 专家注解（后端+前端，7个文件）**
  - migrate_v220.py新增annotations表(id/knowledge_point_id/annotation_type/content/tags/created_at)
  - db_manager.py新增annotations CRUD(add/get_by_kp/delete/get_annotation_summary)，15张表
  - api_server.py新增GET/POST /api/knowledge-points/{id}/annotations注解CRUD
  - api_server.py新增DELETE /api/annotations/{id}删除注解
  - api_server.py新增GET /api/annotation-tags获取预设标签列表
  - api_server.py agree类型自动添加"老唐实战验证"标签
  - review.html新增注解折叠区(每张知识卡片底部，点击展开加载注解列表)
  - review.html新增内联注解表单(5种类型选择+预设标签多选+提交/删除)
  - review.html新增仪表盘第10张卡片(注解统计：总数/各类型/已注解知识点)
- **F045 经验速记（后端+前端，6个文件）**
  - experience_notes.py新增ExperienceNotes模块(V3结构化+入库)
  - experience_notes.py内置ANNOTATION_TAGS预设标签列表(10个)
  - migrate_v220.py新增knowledge_points.source_type字段+虚拟source_file
  - db_manager.py新增source_type筛选支持
  - api_server.py新增POST /api/quicknote经验速记端点
  - api_server.py新增source_type查询参数筛选
  - review.html Tab 2新增经验速记表单区域(标题+内容+类型+关键词)
  - review.html侧边栏新增来源类型筛选(全部/文件提取/经验速记)
  - prompt_templates.py新增EXPERIENCE_STRUCTURE_PROMPT(V3结构化Prompt)
  - prompt_templates.py PROMPT_VERSION升级为v2.2.0
- **系统检查升级**
  - check_system.py升级至v2.5，新增第16项注解与经验速记状态检查
  - check_system.py迁移检查新增annotations表+source_type字段
  - run_checks_json()同步新增注解检查项
- **仪表盘增强**
  - GET /api/dashboard新增annotations统计和manual_kps计数
  - review.html仪表盘从9卡片扩展到10卡片

新增文件：migrate_v220.py, experience_notes.py, 07_Claude.md(项目文件)
修改文件：api_server.py, db_manager.py, review.html, prompt_templates.py, check_system.py

---

## v2.1.2 bugfix -- headless模式input跳过+模型选择下拉框

发布日期：2026-04-08

---

## v2.1.2 第2批 -- 版本重提取+长任务支持+提取管理：F044+F047

发布日期：2026-04-06

---

## v2.1.2 第1批 -- 管理后台框架+仪表盘+工具箱：F046+F033

发布日期：2026-04-05

---

## v2.1.1 第3批 -- 重复检测：F039

发布日期：2026-04-04

---

## v2.1.1 第2批 -- 举一反三提取增强：F038

发布日期：2026-04-03

---

## v2.1.1 第1批 -- bat文件修复+审核界面Bug修复：F040+F041

发布日期：2026-04-03

---

## v2.1.0-d 第2批 -- 政策依赖校验前端：F028审核界面+系统检查

发布日期：2026-03-29

---

## v2.1.0-d 第1.5批 -- 政策依赖校验后端：F028核心模块

发布日期：2026-03-29

---

## v2.1.0-d 第1批 -- 保鲜提醒：F015内容保鲜提醒

发布日期：2026-03-28

---

## v2.1.0-c 第4批 -- 提取质量加固：系统检查升级

发布日期：2026-03-28

---

## v2.1.0-c 第3批 -- 提取质量加固：V3质检+审核反馈统计

发布日期：2026-03-27

---

## v2.1.0-c 第1-2批 -- 提取质量加固：Prompt重写+智能分段+预分析

发布日期：2026-03-27

---

## v2.1.0-b -- 安全网：知识库架构升级迁移（阶段二）
发布日期：2026-03-25

---

## v2.1.0-a -- 安全网：备份恢复（阶段一）
发布日期：2026-03-25

---

## v2.0.0-c -- 变现底座：审核界面全面改版（阶段三）
发布日期：2026-03-23

---

## v2.0.0-b -- 变现底座：Prompt重写+提取引擎三层标签适配（阶段二）
发布日期：2026-03-23

---

## v2.0.0-a -- 变现底座：数据库重构+三层标签配置（阶段一）
发布日期：2026-03-23

---

## v1.1.0 -- 审核增强+分类管理+AI建议+全文搜索
发布日期：2026-03-20

---

## v1.0.1 -- 提取引擎增强
发布日期：2026-03-19

---

## v1.0.0 -- 核心版首次发布
发布日期：2026-03-18
