# Agent 体系手册

> 55个AI Agent,10个部门,一人公司模式。详见 `agents/agent_orchestra.py` DEPARTMENTS 和 `agents/` 目录。

## 部门架构(v2.3.7-part5)

| 部门 | 部长 | 成员数 | 核心KPI |
|------|------|--------|---------|
| CEO办公室 | CEO战略家(V4-Pro) | 7 | 方向正确、财务可控 |
| 内容生产部 | 喂料调度员 | 10 | 月产>=200条高质量KP |
| 客户交付部 | 方案汇编师(V4-Pro) | 4 | 满意度>=85%、续费率>=60% |
| 市场拓展部 | 获客策略师(V4-Pro) | 8 | 月新增付费>=100人 |
| 质量保障部 | 事实核查员 | 6 | 零事实错误、保鲜率>=95% |
| 技术平台部 | 后勤保障部长 | 2 | 99.9%在线、NPU/GPU充分利用 |
| 研发中心 | 研发总监(CTO) | 14 | 技术架构对标大厂标准 |
| 商业变现部 | 收入优化师 | 1 | 月入25万直接责任 |
| 档案管理部 | 档案管理员 | 1 | 文件可检索 |
| 安全合规部 | 安全卫士 | 2 | 零有害内容、零幻觉 |

## Agent 四级类体系(base_agent.py)

```
BaseAgent → think()/evaluate()/ask()
  ├── RoleAgent → simulate_question()
  ├── QualityAgent → audit_batch()
  ├── StrategyAgent(V4-Pro) → deep think
  └── DepartmentChief → list_members()/hold_dept_meeting()/assign_task()/report_to_ceo()
```

## 核心机制

| 机制 | 文件 | 说明 |
|------|------|------|
| 七步会议协议 | meeting_engine.py | 独立表态→强制异议→AI主持→CEO裁决 |
| Agent验证 | agent_verifier.py | 4项上岗测试(专业度+独立性+盈利导向+抗盲从) |
| Agent进化 | agent_evolver.py + evolution_ops.py | 月评估→自动升级→评分<3.0淘汰 |
| 自主循环 | autonomous_controller.py | CEO run()→感知→策略→执行→学习→停滞检测 |
| 安全双门禁 | safety_agents.py | SafetyFilter(入口)+HallucinationGuard(出口) |
| 管道全自动 | pipeline_director.py + run_pipeline.py | 5阶段日循环>=95%自动化 |

## 部门操作中心(v2.3.7-part5)

每个部门有 ops 模块驱动日常运转:

| 部门 | Ops文件 |
|------|---------|
| 内容生产部 | content_production_ops.py |
| 客户交付部 | client_delivery_ops.py |
| 市场拓展部 | market_expansion_ops.py |
| 质量+安全 | quality_safety_ops.py |
| 商业变现部 | revenue_ops.py |
| 演进层 | evolution_ops.py |
| 研发中心 | rd_center_ops.py |

## 全局任务注册表(v2.3.7-part5)

`agents/global_task_registry.py` — CEO系统性思维基础设施:
- 所有任务注册/追踪/验证/闭环
- 缺失领域主动扫描
- 失败任务自动纠偏

## 特殊Agent

| Agent | 部门 | 职责 |
|-------|------|------|
| QA系统架构师 | 研发中心 | QA助手持续迭代优化(检索/Prompt/评测) |
| 3xSkillScout | 研发中心 | GitHub技能侦察(NLP/政府数据/安全) |
| 5个设计Agent | 冷冻 | pre-revenue,收入验证后激活 |
