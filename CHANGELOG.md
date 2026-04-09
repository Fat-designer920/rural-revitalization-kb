# 变更日志

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

变更内容：
- **extractor.py headless模式bugfix**
  - 新增self._headless标志位，set_model()时自动设为True
  - check_duplicate(): headless时自动重新分析，不阻塞等待用户输入
  - _pre_analyze(): headless时预分析3次失败自动跳过预分析
  - 低价值文件(评分<=2): headless时自动继续提取
  - 高费用(>5元): headless时自动继续提取
- **review.html模型选择下拉框**
  - 提取管理区域新增"提取模型"下拉选择框(R1深度推理/V3快速提取)
  - 一键提取和版本重提取均读取下拉框选择的模型值

修改文件：extractor.py, review.html

---

## v2.1.2 第2批 -- 版本重提取+长任务支持+提取管理：F044+F047

发布日期：2026-04-06

变更内容：
- **F044 版本重提取**
  - api_server.py新增GET /api/tools/reextract-scan扫描旧版本知识点
  - api_server.py新增POST /api/tasks/reextract版本重提取
  - db_manager.py新增get_reextract_scan()+delete_kps_by_source_file()
  - review.html新增版本重提取面板
- **F047 长任务后台执行**
  - api_server.py新增_task全局字典+GET /api/tasks/progress+POST preprocess/extract
  - extractor.py新增progress_callback+headless运行模式
  - review.html新增长任务进度面板
- **提取管理**
  - review.html Tab 2新增提取管理区域

修改文件：api_server.py, db_manager.py, extractor.py, review.html

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
