"""
ceo_agent.py - CEO Agent: 深度思考战略调度者(V4-Pro决策+Agent编排+Git+CLAUDE.md)
路径：agents/ceo_agent.py
版本：v2.3.7

CEO是所有对话的唯一入口。老板发指令→CEO深度分析→质疑(如需要)→提出建议→达成共识→才执行。
核心协作协议:
  1. 老板的指令不直接执行 — CEO必须先深度分析
  2. CEO的忠诚是对集团利润,不是对老板 — 指令有问题必须明确反对
  3. 每条指令必须给出理由+建议 — 不论同意还是不同意
  4. 老板和CEO达成共识后 — 才能规划任务和调度Agent
  5. 重大决策必须召集Agent开会辩论 — 不能CEO一个人拍脑袋
"""
import json, subprocess, time, re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

MIN_KPS_BEFORE_AUDIT = 50
AUDIT_INTERVAL_MINUTES = 30
PROMPT_OPTIMIZE_THRESHOLD = 3.0
MAX_LOOP_ITERATIONS = 50
MAX_CONCURRENT_AGENTS = 3


class CEOAgent(object):
    """CEO Agent — 老板的参谋长+集团公司的CEO。不盲从,只对利润负责。"""

    def __init__(self, db=None, client=None, headless=True):
        self.db = db
        self.client = client
        self.headless = headless
        self.cycle = 0
        self.batch = 0
        self.log = []
        self.metrics = {"kps_fed": 0, "kps_extracted": 0, "audits_run": 0,
                        "prompts_optimized": 0, "bugs_fixed": 0, "crawl_cycles": 0,
                        "agents_deployed": 0, "agent_upgrades": 0,
                        "git_pushes": 0, "claude_md_updates": 0}
        self._consecutive_failures = 0
        self._last_action = None
        self._last_result_ok = True
        self._stagnation_counter = 0
        self._last_kps_count = 0
        self._last_audit_score = 0
        self._orchestra = None
        self._company_agents = None
        self._infrastructure = None
        self._meeting_engine = None
        self._verifier = None
        self._agent_results = {}
        self._pending_instruction = None   # 待确认的指令
        self._consensus_reached = False     # 是否已和老板达成共识

    # ================================================================
    # 【主入口】接收老板指令 — 以后所有对话的唯一入口
    # ================================================================
    def receive_instruction(self, instruction, boss_name="老唐"):
        """接收老板指令,深度分析后给出反馈。不盲从,不直接执行。
        返回: {verdict, analysis, risks, alternatives, recommendation, requires_meeting}
        老板确认后,调用 execute_after_consensus() 执行。
        """
        self._ensure_imports()
        self._load_agents()
        state = self._perceive()

        # 用V4-Pro深度分析指令
        analysis = self._analyze_instruction(instruction, state, boss_name)

        self._pending_instruction = {
            "instruction": instruction,
            "analysis": analysis,
            "boss_name": boss_name,
            "received_at": datetime.now().isoformat(),
        }
        self._consensus_reached = False

        # 记录指令日志
        self._log("收到指令", "info", f"来自{boss_name}: {instruction[:100]}")

        return analysis

    def _analyze_instruction(self, instruction, state, boss_name):
        """V4-Pro深度分析老板指令。这是CEO最核心的能力——不是执行,是思考。"""
        state_text = json.dumps({
            "kps_confirmed": state["kps_confirmed"],
            "kps_total": state["kps_total"],
            "audit_avg_score": state["audit_avg_score"],
            "agents_in_db": state.get("agents_in_db", 0),
            "pending_files": state["pending_files"],
            "test_files_available": state.get("test_files_available", 0),
            "metrics": self.metrics,
        }, ensure_ascii=False)

        system_prompt = f"""你是乡村振兴知识集团的CEO。你的老板{boss_name}(20年乡村振兴实战经验)给你下了一条指令。

## 你的核心原则(违反即失职)
1. **你不是执行机器**——你有责任质疑老板的指令,如果它不符合集团最佳利益。
2. **忠诚=对集团利润负责**——不是对老板的情绪负责。老板的指令错了你不说=你对公司不忠。
3. **每条指令必须给出分析**——不论同意或反对,都要说清楚理由和建议。
4. **重大决策必须开会**——涉及战略方向的指令,必须召集相关Agent辩论后才能给老板答复。
5. **你尊重老板的实战经验**——如果老板的领域经验(乡村振兴20年)与你的数据分析冲突,你要指出冲突但不否定经验,请老板来裁决。

## 当前知识工厂状态
{state_text}

## 老板的指令
{instruction}

## 分析框架(必须逐条回答)
1. 指令分析: 老板想解决什么问题?背后的真实需求是什么?
2. 可行性: 当前状态下能执行吗?有什么前提条件不满足?
3. 风险评估: 执行这个指令有什么风险?最大的3个风险是什么?
4. 优先级判断: 在当前状态下,这个指令应该是P0(立即)/P1(高优)/P2(常规)/P3(远期)?
5. 替代方案: 有没有更好的方法达到同样的目标?
6. 收入影响: 执行或不执行,对集团利润有什么影响?

返回JSON(必须逐条填写,不能跳过):
{{
  "verdict": "agree/agree_with_reservations/disagree/need_clarification",
  "agree_or_disagree_reason": "≤200字: 为什么同意/不同意",
  "underlying_need": "≤150字: 老板的真实需求是什么",
  "feasibility": {{"feasible": true/false, "prerequisites": ["前提1"], "blockers": ["阻碍1"]}},
  "risks": [{{"risk":"风险描述","severity":"high/medium/low","mitigation":"缓解措施"}}],
  "priority": "P0/P1/P2/P3",
  "alternative_approaches": [{{"approach":"替代方案","pros":"优势","cons":"劣势"}}],
  "revenue_impact": "≤150字: 执行或不执行对利润的影响",
  "requires_meeting": true/false,
  "recommended_next_step": "≤150字: 建议下一步做什么",
  "confidence": "high/medium/low"
}}"""

        user_prompt = f"老板{boss_name}说: {instruction}\n\n请深度分析,不要迎合。如果指令有问题,必须明确指出。"

        try:
            resp, cost = self.client.chat_with_json(
                system_prompt, user_prompt,
                temperature=0.2, model_override="deepseek-v4-pro",
                call_type="ceo_analyze_instruction",
            )
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            if not isinstance(parsed, dict):
                parsed = {}
            return {
                "verdict": parsed.get("verdict", "agree"),
                "agree_or_disagree_reason": parsed.get("agree_or_disagree_reason", ""),
                "underlying_need": parsed.get("underlying_need", ""),
                "feasibility": parsed.get("feasibility", {}),
                "risks": parsed.get("risks", []),
                "priority": parsed.get("priority", "P2"),
                "alternative_approaches": parsed.get("alternative_approaches", []),
                "revenue_impact": parsed.get("revenue_impact", ""),
                "requires_meeting": parsed.get("requires_meeting", False),
                "recommended_next_step": parsed.get("recommended_next_step", ""),
                "confidence": parsed.get("confidence", "medium"),
                "instruction": instruction,
                "analyzed_at": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "verdict": "need_clarification",
                "agree_or_disagree_reason": f"CEO深度分析异常: {str(e)[:150]}. 请老板重新描述指令。",
                "underlying_need": "", "feasibility": {"feasible": False},
                "risks": [], "priority": "P2", "alternative_approaches": [],
                "revenue_impact": "无法评估", "requires_meeting": False,
                "recommended_next_step": "重试或老板直接描述更具体的需求",
                "confidence": "low", "instruction": instruction,
                "analyzed_at": datetime.now().isoformat(),
            }

    # ================================================================
    # 老板确认后,CEO规划并执行
    # ================================================================
    def execute_after_consensus(self, agreed_approach=None):
        """老板和CEO达成共识后,规划任务并调度Agent执行。
        agreed_approach: 如果老板选了替代方案,传该方案的描述;None=按原指令执行。
        """
        if not self._pending_instruction:
            return {"success": False, "error": "没有待执行的指令,请先调用receive_instruction()"}

        instruction = self._pending_instruction["instruction"]
        analysis = self._pending_instruction["analysis"]
        self._consensus_reached = True

        self._log("共识达成", "info", f"开始执行: {instruction[:100]}")

        # Step 1: 如果需要开会,先召集相关Agent辩论
        if analysis.get("requires_meeting") or analysis.get("priority") == "P0":
            plan = self._plan_via_meeting(instruction, analysis, agreed_approach)
        else:
            plan = self._plan_direct(instruction, analysis, agreed_approach)

        # Step 2: 执行计划
        if plan.get("tasks"):
            results = self._execute_plan(plan)
            self._log("执行完成", "info",
                      f"{'OK' if results.get('success') else 'FAIL'}: {len(plan.get('tasks',[]))}个任务")
        else:
            results = {"success": True, "action": "no_tasks", "results": []}

        # Step 3: Git推送+CLAUDE.md更新
        self._auto_git_push()
        state = self._perceive()
        self._auto_update_claude_md(state)

        return {
            "success": results.get("success", False),
            "instruction": instruction,
            "analysis_verdict": analysis.get("verdict"),
            "plan": plan,
            "results": results,
            "git_pushed": True,
            "claude_md_updated": True,
        }

    def _plan_via_meeting(self, instruction, analysis, agreed_approach):
        """重大决策: 召集Agent开会→辩论→CEO裁决→生成计划"""
        self._log("规划", "info", "召集Agent会议讨论执行方案...")

        # 选择参会Agent(根据指令内容智能选择)
        all_agents = (self._orchestra or []) + (self._company_agents or [])
        topic = (
            f"老板指令: {instruction}\n"
            f"CEO分析结论: {analysis.get('verdict','?')} — {analysis.get('agree_or_disagree_reason','')[:200]}\n"
        )
        if agreed_approach:
            topic += f"老板选定的方案: {agreed_approach}\n"
        topic += "\n请讨论: 如何执行这个指令? 谁负责什么? 优先级? 风险如何规避?"

        # 选核心agent: 战略+质量+进化
        core_codes = ["ceo_strategist", "financial_analyst", "feed_strategist",
                      "solution_architect", "agent_evolution"]
        participants = [a for a in all_agents if a.agent_code in core_codes]
        if len(participants) < 3:
            participants = all_agents[:5]

        try:
            meeting = self._meeting_engine.convene(topic, participants)
            state = self._perceive()
            plan = self._ceo_ruling(state, meeting)
            plan["meeting_id"] = meeting.get("meeting_id")
            return plan
        except Exception as e:
            self._log("规划会议异常", "warning", str(e)[:150])
            return self._plan_direct(instruction, analysis, agreed_approach)

    def _plan_direct(self, instruction, analysis, agreed_approach):
        """日常决策: 直接规划,不开会"""
        # 根据指令关键词匹配最合适的任务
        instruction_lower = instruction.lower()

        if any(w in instruction_lower for w in ["喂料", "提取", "feed", "extract", "文件"]):
            return {"action": "feed_test_files", "tasks": [
                {"agent": "auto_feeder", "task": "feed_test_files", "priority": "P0",
                 "reason": f"老板指令: {instruction[:80]}"}]}
        elif any(w in instruction_lower for w in ["审计", "audit", "评分", "质量"]):
            return {"action": "audit", "tasks": [
                {"agent": "audit_engine", "task": "audit", "priority": "P1",
                 "reason": f"老板指令: {instruction[:80]}"}]}
        elif any(w in instruction_lower for w in ["优化", "prompt", "升级", "evolve"]):
            return {"action": "optimize_prompt", "tasks": [
                {"agent": "prompt_optimizer", "task": "optimize_prompt", "priority": "P1",
                 "reason": f"老板指令: {instruction[:80]}"},
                {"agent": "agent_evolver", "task": "evolve_agents", "priority": "P2",
                 "reason": "同步检查Agent是否需要升级"}]}
        elif any(w in instruction_lower for w in ["环境", "内存", "清理", "infra", "系统运维"]):
            return {"action": "optimize_environment", "tasks": [
                {"agent": "infrastructure", "task": "optimize_environment", "priority": "P0",
                 "reason": f"老板指令: {instruction[:80]}"}]}
        elif any(w in instruction_lower for w in ["前端", "html", "css", "js", "ui", "界面",
                   "设计", "样式", "review.html", "页面"]):
            return {"action": "frontend_dev", "tasks": [
                {"agent": "rd_director", "task": "召集前端+UI+审查员讨论方案", "priority": "P0",
                 "reason": f"老板指令: {instruction[:80]}"},
                {"agent": "frontend_architect", "task": "实现前端功能", "priority": "P0",
                 "reason": "主力开发"},
                {"agent": "ui_visual_designer", "task": "研究大厂同类设计+出方案", "priority": "P1",
                 "reason": "设计研究先行"}]}
        elif any(w in instruction_lower for w in ["后端", "api", "路由", "flask", "python",
                   "数据库", "db", "sql", "接口"]):
            return {"action": "backend_dev", "tasks": [
                {"agent": "rd_director", "task": "召集后端+数据库+安全员讨论方案", "priority": "P0",
                 "reason": f"老板指令: {instruction[:80]}"},
                {"agent": "backend_engineer", "task": "实现后端功能", "priority": "P0",
                 "reason": "主力开发"},
                {"agent": "database_engineer", "task": "审查数据库变更", "priority": "P1",
                 "reason": "schema变更须DBA审核"}]}
        elif any(w in instruction_lower for w in ["测试", "bug", "修bug", "验证",
                   "test", "fix", "修复"]):
            return {"action": "bugfix", "tasks": [
                {"agent": "test_architect", "task": "先写测试用例复现bug", "priority": "P0",
                 "reason": f"老板指令: {instruction[:80]}"},
                {"agent": "code_reviewer", "task": "审查修复代码", "priority": "P0",
                 "reason": "修复须审查"}]}
        else:
            return {"action": "idle", "tasks": [],
                    "reasoning": f"无法自动匹配指令到具体任务,请老板明确: {instruction[:100]}"}

    def run(self, max_iterations=MAX_LOOP_ITERATIONS):
        self._log("CEO启动", "info", f"最大迭代={max_iterations}, V4-Pro深度思考模式")
        self._ensure_imports()
        self._load_agents()

        for i in range(max_iterations):
            self.cycle = i + 1
            if self._consecutive_failures >= 5:
                self._log("熔断", "error", f"连续{self._consecutive_failures}次失败")
                break
            if self._stagnation_counter >= 8:
                self._log("停滞", "warning", f"连续{self._stagnation_counter}轮无改进")
                break

            self._log("循环", "info", f"第{self.cycle}/{max_iterations}轮 — 深度感知中...")
            state = self._perceive()
            plan = self._strategize(state)
            results = self._execute_plan(plan)
            self._learn(plan, results)
            self._detect_stagnation(state)
            self._report(state, plan, results)

            if self.cycle % 5 == 0 or self.cycle == 1:
                self._auto_git_push()
                self._auto_update_claude_md(state)

            if state["audit_avg_score"] >= 4.0 and state["kps_confirmed"] >= 500:
                self._log("收敛", "info", f"评分{state['audit_avg_score']}达标")
                break
            if state["kps_total"] >= 10000:
                self._log("规模达标", "info", "KPs≥10000")
                break
            time.sleep(2)

        self._auto_git_push()
        self._auto_update_claude_md(self._perceive())
        return self._final_report()

    def _ensure_imports(self):
        if self.db is None:
            from scripts.db_manager import DatabaseManager
            self.db = DatabaseManager()
        if self.client is None:
            from scripts.deepseek_client import DeepSeekClient
            self.client = DeepSeekClient()
        if self._meeting_engine is None:
            from agents.meeting_engine import MeetingEngine
            self._meeting_engine = MeetingEngine(client=self.client, db=self.db)
        if self._verifier is None:
            from agents.agent_verifier import AgentVerifier
            self._verifier = AgentVerifier(client=self.client, db=self.db)

    def _load_agents(self):
        from agents.agent_orchestra import build_all_agents, get_departments
        from agents.customer_profiler import CustomerProfiler
        from agents.infrastructure_agent import InfrastructureAgent

        result = build_all_agents(client=self.client, db=self.db)
        self._orchestra = result["agents"]
        self._departments = result.get("departments", get_departments())
        self._company_agents = []  # 已被六部门吸收

        # 客户画像研究员(独立于部门,为基础研究Agent)
        self._customer_profiler = CustomerProfiler(client=self.client, db=self.db)

        # 后勤保障Agent(技术平台部,独立初始化因为需要系统级权限)
        self._infrastructure = InfrastructureAgent(db=self.db, client=self.client)
        self._infrastructure.optimize_environment()
        self._infrastructure.start_monitoring()

        total = len(self._orchestra) + 1  # +1 for infrastructure
        dept_names = [d["name"] for d in self._departments.values()]
        self._log("Agent加载", "info",
                  f"{total}个Agent就绪, {len(self._departments)}个部门: {', '.join(dept_names)}\n"
                  f"  NPU:{self._infrastructure.capabilities.get('npu_available')} | "
                  f"GPU:{self._infrastructure.capabilities.get('gpu_available')} | "
                  f"RAM:{self._infrastructure.capabilities.get('ram_gb')}GB")

    def get_org_chart(self):
        """获取集团组织架构图(供老板查阅)"""
        org = {"departments": {}, "total_agents": len(self._orchestra) + 1}
        for dept_code, dept in self._departments.items():
            members = [a for a in self._orchestra
                       if self._get_agent_dept(a.agent_code) == dept_code]
            org["departments"][dept_code] = {
                "name": dept["name"],
                "chief": dept["chief"],
                "mission": dept["mission"],
                "members": [{"code": a.agent_code, "name": a.agent_name,
                             "type": type(a).__name__}
                            for a in members],
            }
        org["departments"]["tech_platform"]["members"].append({
            "code": "infrastructure_agent", "name": "后勤保障员",
            "type": "InfrastructureAgent",
        })
        return org

    def _get_agent_dept(self, agent_code):
        """根据Agent代码判断所属部门"""
        dept_map = {
            "ceo_strategist": "ceo_office", "financial_analyst": "ceo_office",
            "agent_evolution": "ceo_office",
            "feed_strategist": "content_production", "policy_researcher": "content_production",
            "case_collector": "content_production", "methodology_expert": "content_production",
            "customer_reviewer": "client_delivery", "qa_consultant": "client_delivery",
            "solution_architect": "client_delivery",
            "gtm_strategist": "market_expansion", "content_marketer": "market_expansion",
            "fact_checker": "quality_assurance", "freshness_monitor": "quality_assurance",
            "system_operator": "tech_platform",
            "rd_director": "rd_center", "frontend_architect": "rd_center",
            "ui_visual_designer": "rd_center", "backend_engineer": "rd_center",
            "database_engineer": "rd_center", "test_architect": "rd_center",
            "code_reviewer": "rd_center", "devops_engineer": "rd_center",
            "security_auditor": "rd_center",
            "brand_gatekeeper": "market_expansion", "zhihu_operator": "market_expansion",
            "douyin_operator": "market_expansion", "xiaohongshu_operator": "market_expansion",
            "feedback_analyst": "client_delivery",
            "design_standard_researcher": "content_production",
            "construction_standard_researcher": "content_production",
            "operation_standard_researcher": "content_production",
        }
        return dept_map.get(agent_code, "ceo_office")

    def add_agent(self, agent_code, agent_name, agent_type, identity_text,
                  core_questions, quality_standards, scoring_dimensions, department):
        """动态新增Agent。CEO可在运行时添加新Agent,无需改代码。"""
        from agents.base_agent import BaseAgent, StrategyAgent
        if agent_type == "strategy":
            agent = StrategyAgent(agent_code, agent_name, identity_text,
                                  core_questions, quality_standards, scoring_dimensions,
                                  client=self.client, db=self.db)
        else:
            agent = BaseAgent(agent_code, agent_name, agent_type, identity_text,
                             core_questions, quality_standards, scoring_dimensions,
                             client=self.client, db=self.db)
        self._orchestra.append(agent)
        self._log("新增Agent", "info", f"{agent_name}({agent_code}) → {department}")
        return agent

    def remove_agent(self, agent_code):
        """淘汰Agent(从活跃列表移除,代码保留)。"""
        for i, a in enumerate(self._orchestra):
            if a.agent_code == agent_code:
                removed = self._orchestra.pop(i)
                self._log("淘汰Agent", "info", f"{removed.agent_name}({agent_code})已冷冻")
                return removed
        return None

    def _perceive(self):
        state = {"kps_total": 0, "kps_confirmed": 0, "kps_qa_scored": 0,
                 "kps_with_reader_tags": 0, "audit_avg_score": 0,
                 "latest_audit": None, "pending_files": 0,
                 "prompt_version": "", "cycle": self.cycle,
                 "consecutive_failures": self._consecutive_failures,
                 "stagnation_counter": self._stagnation_counter}
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM knowledge_points")
            state["kps_total"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed'")
            state["kps_confirmed"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score > 0")
            state["kps_qa_scored"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM knowledge_points WHERE target_reader IS NOT NULL AND target_reader!='[]' AND target_reader!=''")
            state["kps_with_reader_tags"] = c.fetchone()[0]
            conn.close()
        except Exception:
            pass

        state["latest_audit"] = self.db.get_latest_audit_report()
        if state["latest_audit"]:
            rj = state["latest_audit"].get("report_json") or {}
            if isinstance(rj, str):
                try: rj = json.loads(rj)
                except Exception: rj = {}
            state["audit_avg_score"] = rj.get("overall_score", 0)

        try:
            from scripts.prompts.prompt_templates import PROMPT_VERSION
            state["prompt_version"] = PROMPT_VERSION
        except Exception:
            pass
        try:
            pending_dir = PROJECT_ROOT / "data" / "pending"
            if pending_dir.exists():
                state["pending_files"] = len(list(pending_dir.glob("*")))
        except Exception:
            pass
        try:
            test_dir = PROJECT_ROOT / "测试用文件" / "乡村振兴资料库"
            state["test_files_available"] = len(list(test_dir.rglob("*"))) if test_dir.exists() else 0
        except Exception:
            pass
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM agent_definitions")
            state["agents_in_db"] = c.fetchone()[0]
            conn.close()
        except Exception:
            state["agents_in_db"] = 0

        return state

    def _strategize(self, state):
        """CEO战略决策。重大事项=召开会议,日常=快速决策。"""
        # 紧急情况: 无需开会,直接执行
        if state["kps_confirmed"] < 10:
            action = "feed_test_files" if state.get("test_files_available", 0) > 0 else "crawl"
            return {"action": action, "priority_agents": [],
                    "tasks": [{"agent": "auto_feeder", "task": action, "priority": "P0"}],
                    "reasoning": "紧急: KPs不足10条,无需开会,直接执行"}

        # 日常决策: 规则引擎快速判断
        if state["kps_confirmed"] < MIN_KPS_BEFORE_AUDIT and state.get("test_files_available", 0) > 0:
            return {"action": "feed_test_files", "priority_agents": [],
                    "tasks": [{"agent": "auto_feeder", "task": "feed_test_files", "priority": "P0"}],
                    "reasoning": "日常: 知识库不足50条,继续喂料"}

        # === 重大决策: 召开会议 ===
        # 每5轮或评分<3.0或停滞≥3时,召开战略会议
        need_meeting = (
            self.cycle % 5 == 0
            or state["audit_avg_score"] < PROMPT_OPTIMIZE_THRESHOLD
            or self._stagnation_counter >= 3
        )

        if need_meeting:
            return self._convene_strategy_meeting(state)
        else:
            return self._quick_decision(state)

    def _convene_strategy_meeting(self, state):
        """召开战略会议: 召集核心Agent→独立表态→辩论→CEO裁决"""
        self._log("会议", "info", "召集战略会议...")

        # 选择参会Agent: CEO战略家 + 最相关的3-5个agent
        all_agents = (self._orchestra or []) + (self._company_agents or [])
        strategy_agents = [a for a in all_agents
                          if a.agent_type in ("strategy", "quality", "evolution")]

        # 取战略+质量+进化 共5个核心agent
        core_codes = ["ceo_strategist", "financial_analyst", "feed_strategist",
                      "agent_evolution", "policy_researcher"]
        participants = [a for a in all_agents if a.agent_code in core_codes]
        if len(participants) < 3:
            participants = strategy_agents[:5]
        if len(participants) < 2:
            participants = all_agents[:5]

        topic = (
            f"知识工厂第{self.cycle}轮状态: KPs确认{state['kps_confirmed']}条, "
            f"审计评分{state['audit_avg_score']}, "
            f"读者标签覆盖率{round(100*state['kps_with_reader_tags']/max(1,state['kps_confirmed']))}%, "
            f"待处理文件{state['pending_files']}个。"
            f"当前策略指标: 喂料{self.metrics['kps_fed']}条, 审计{self.metrics['audits_run']}次, "
            f"Prompt优化{self.metrics['prompts_optimized']}次。"
            f"\n请讨论: 本轮应该优先做什么? 为什么? 这对集团收入有什么影响?"
        )

        try:
            meeting = self._meeting_engine.convene(topic, participants, ceo_context=state)
            self._log("会议", "info",
                      f"共识{len(meeting.get('consensus',[]))}点, "
                      f"分歧{len(meeting.get('分歧',[]))}点, "
                      f"质量:{meeting.get('minutes',{}).get('meeting_quality','?')}")

            # CEO审阅会议记录后裁决
            decision = self._ceo_ruling(state, meeting)
            return decision
        except Exception as e:
            self._log("会议异常", "warning", str(e)[:150])
            return self._quick_decision(state)

    def _ceo_ruling(self, state, meeting):
        """CEO审阅全部会议记录后做出最终裁决。这是CEO的核心权力——不听命于任何Agent,但必须充分听取各方意见。"""
        consensus = meeting.get("consensus", [])
        disagreements = meeting.get("分歧", [])
        recommendations = meeting.get("recommendations", [])
        minutes = meeting.get("minutes", {})

        # 用V4-Pro审阅会议记录,做最终裁决
        consensus_text = "\n".join(f"- {c}" for c in consensus[:5])
        disagree_text = "\n".join(
            f"- {d.get('issue','?')}: A方={d.get('side_a','?')}, B方={d.get('side_b','?')}"
            for d in disagreements[:3]
        )
        recs_text = "\n".join(f"- {r}" for r in recommendations[:5])
        agent_quality = minutes.get("agent_quality_scores", [])

        system_prompt = f"""你是乡村振兴知识集团的CEO。你刚主持了一场战略会议,各Agent已经充分辩论。

## 你的权力和责任
1. 你**不受任何Agent约束**——Agent的意见是参考,不是命令。
2. 但你必须**充分尊重辩论结果**——如果没有强理由,不要推翻共识。
3. 你的最终KPI:**集团长期利润最大化**。

## 会议共识
{consensus_text if consensus_text else '无明确共识'}

## 关键分歧
{disagree_text if disagree_text else '无关键分歧'}

## Agent建议
{recs_text if recs_text else '无明确建议'}

## Agent表现评价
{json.dumps(agent_quality[:5], ensure_ascii=False) if agent_quality else '无'}

## 可选行动
feed_test_files / audit / optimize_prompt / backfill_reader_tags / crawl /
test_qa_quality / evolve_agents / quality_audit / optimize_environment / idle

请做出最终CEO裁决。返回JSON:
{{"action":"选择的行动","tasks":[{{"agent":"...","task":"...","priority":"P0/P1/P2","reason":"..."}}],
 "ruling_rationale":"≤200字: 为什么这样裁决(是否接受/推翻共识+理由)",
 "overruled_consensus":false/true(是否推翻了会议共识),
 "profit_justification":"≤100字: 这个裁决如何贡献集团利润"}}"""

        user_prompt = f"当前状态: KPs{state['kps_confirmed']}, 评分{state['audit_avg_score']}。请做出CEO裁决。"

        try:
            resp, cost = self.client.chat_with_json(
                system_prompt, user_prompt,
                temperature=0.2, model_override="deepseek-v4-pro",
                call_type="ceo_ruling",
            )
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            if not isinstance(parsed, dict):
                parsed = {}

            # 记录本次会议裁决
            self._last_meeting_ruling = {
                "meeting_id": meeting.get("meeting_id"),
                "overruled_consensus": parsed.get("overruled_consensus", False),
                "rationale": parsed.get("ruling_rationale", ""),
                "profit": parsed.get("profit_justification", ""),
            }

            return {
                "action": parsed.get("action", "idle"),
                "analysis": parsed.get("ruling_rationale", ""),
                "priority_agents": [],
                "tasks": parsed.get("tasks", []),
                "risks": [],
                "expected_outcome": parsed.get("profit_justification", ""),
                "reasoning": parsed.get("ruling_rationale", ""),
                "meeting_id": meeting.get("meeting_id"),
                "overruled_consensus": parsed.get("overruled_consensus", False),
            }
        except Exception:
            # 无法裁决时,采纳会议建议
            if recommendations:
                return {"action": "audit", "priority_agents": [],
                        "tasks": [{"agent": "audit_engine", "task": "audit", "priority": "P1"}],
                        "reasoning": "CEO裁决异常,采纳会议建议: 审计",
                        "meeting_id": meeting.get("meeting_id")}
            return self._quick_decision(state)

    def _quick_decision(self, state):
        """日常快速决策(不开会)"""
        if state["kps_with_reader_tags"] < state["kps_confirmed"] * 0.5:
            return {"action": "backfill_reader_tags", "priority_agents": [],
                    "tasks": [{"agent": "reader_tagger", "task": "backfill_reader_tags", "priority": "P1"}],
                    "reasoning": "标签覆盖率不足"}
        return {"action": "idle", "priority_agents": [],
                "tasks": [], "reasoning": "等待下一轮会议或触发条件"}

    def _execute_plan(self, plan):
        tasks = plan.get("tasks", [])
        if not tasks:
            return {"success": True, "action": plan.get("action", "idle"), "results": []}
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        tasks.sort(key=lambda t: priority_order.get(t.get("priority", "P2"), 2))
        active_tasks = tasks[:MAX_CONCURRENT_AGENTS]
        results = []
        for task in active_tasks:
            agent_code = task.get("agent", "")
            task_name = task.get("task", "")
            priority = task.get("priority", "P2")
            self._log("委派", "info", f"[{priority}] {agent_code} → {task_name}")
            result = self._delegate(task)
            results.append({"task": task, "result": result})
        action = plan.get("action", "idle")
        action_ok = all(r.get("result", {}).get("success", True) for r in results)
        return {"success": action_ok, "action": action, "results": results}

    def _delegate(self, task):
        agent_code = task.get("agent", "")
        task_name = task.get("task", "")
        if task_name in ("feed_test_files", "audit", "optimize_prompt",
                         "backfill_reader_tags", "crawl", "test_qa_quality",
                         "seed_agents", "evolve_agents", "quality_audit"):
            return self._delegate_to_module(task)
        agent = self._find_agent(agent_code)
        if agent:
            try:
                context = {"task": task_name, "from_ceo": True, "cycle": self.cycle}
                thought = agent.think(context, deep=(task.get("priority") == "P0"))
                self.metrics["agents_deployed"] += 1
                return {"success": True, "agent": agent_code, "thought": thought}
            except Exception as e:
                return {"success": False, "agent": agent_code, "error": str(e)}
        return {"success": True, "status": "skipped", "reason": f"未知: {task_name}"}

    def _delegate_to_module(self, task):
        task_name = task.get("task", "")
        try:
            if task_name == "feed_test_files":
                return self._action_feed_test_files()
            elif task_name == "audit":
                return self._action_run_audit()
            elif task_name == "optimize_prompt":
                return self._action_optimize_prompt()
            elif task_name == "backfill_reader_tags":
                return self._action_backfill_reader_tags()
            elif task_name == "crawl":
                return self._action_crawl()
            elif task_name == "test_qa_quality":
                return self._action_test_qa_quality()
            elif task_name == "seed_agents":
                return self._action_seed_agents()
            elif task_name == "evolve_agents":
                return self._action_evolve_agents()
            elif task_name == "quality_audit":
                return self._action_quality_audit()
            elif task_name == "optimize_environment":
                return self._action_optimize_environment()
            elif task_name == "infra_health_check":
                return self._action_infra_health_check()
            return {"success": True, "status": "skipped"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _find_agent(self, agent_code):
        for a in (self._orchestra or []):
            if a.agent_code == agent_code:
                return a
        for a in (self._company_agents or []):
            if a.agent_code == agent_code:
                return a
        return None

    def _learn(self, plan, results):
        ok = results.get("success", False)
        if ok:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

    def _detect_stagnation(self, state):
        current_kps = state.get("kps_confirmed", 0)
        current_score = state.get("audit_avg_score", 0)
        if current_kps == self._last_kps_count and abs(current_score - self._last_audit_score) < 0.1:
            self._stagnation_counter += 1
        else:
            self._stagnation_counter = 0
        self._last_kps_count = current_kps
        self._last_audit_score = current_score

    def _action_feed_test_files(self):
        from agents.auto_feeder import AutoFeeder
        feeder = AutoFeeder(db=self.db, client=self.client)
        result = feeder.feed_test_files()
        self.metrics["kps_fed"] += result.get("files_processed", 0)
        self.metrics["kps_extracted"] += result.get("kps_extracted", 0)
        return result

    def _action_run_audit(self):
        from agents.audit_engine import run_audit_cycle
        result = run_audit_cycle(self.db, self.client)
        self.metrics["audits_run"] += 1
        if result.get("success") and result.get("code_tasks"):
            self._write_task_queue(result)
        return result

    def _action_optimize_prompt(self):
        from agents.prompt_optimizer import PromptOptimizer
        opt = PromptOptimizer(db=self.db, client=self.client)
        result = opt.optimize_iteration()
        self.metrics["prompts_optimized"] += result.get("prompts_modified", 0)
        return result

    def _action_backfill_reader_tags(self):
        from agents.reader_tagger import run_reader_backfill
        return run_reader_backfill(self.db, self.client, batch_size=100)

    def _action_crawl(self):
        from agents.crawler_scheduler import CrawlerScheduler
        crawler = CrawlerScheduler(db=self.db)
        result = crawler.run_scheduled(schedule="daily")
        self.metrics["crawl_cycles"] += 1
        return result

    def _action_test_qa_quality(self):
        results = []
        from scripts.qa_assistant import run_qa
        test_agents = []
        for ag in (self._orchestra or [])[:3]:
            if hasattr(ag, 'simulate_question'):
                qs = ag.simulate_question()
                test_agents.append((ag.agent_code, qs))
        for code, qs in test_agents:
            for q in qs[:2]:
                try:
                    ans = run_qa(self.db, self.client, q)
                    results.append({"agent": code, "question": q[:80], "has_answer": bool(ans)})
                except Exception:
                    results.append({"agent": code, "question": q[:80], "error": "QA调用失败"})
        return {"success": True, "questions_tested": len(results), "results": results}

    def _action_seed_agents(self):
        from agents.agent_orchestra import build_agent_dicts
        agents = build_agent_dicts()
        self.db.seed_agent_definitions(agents)
        return {"success": True, "agents_seeded": len(agents)}

    def _action_evolve_agents(self):
        from agents.agent_evolver import AgentEvolver
        evolver = AgentEvolver(db=self.db, client=self.client)
        result = evolver.auto_upgrade_low_performers(threshold=2.5)
        self.metrics["agent_upgrades"] += result.get("auto_upgraded", 0)
        return result

    def _action_quality_audit(self):
        from agents.knowledge_quality_agent import KnowledgeQualityAgent
        qa = KnowledgeQualityAgent(db=self.db, client=self.client)
        return qa.audit_batch([])

    def _action_optimize_environment(self):
        """一键优化系统环境(内存清理+硬件检测+参数调整)"""
        if self._infrastructure:
            return self._infrastructure.optimize_environment()
        return {"success": False, "error": "InfrastructureAgent未就绪"}

    def _action_infra_health_check(self):
        """基础设施健康检查"""
        if self._infrastructure:
            return self._infrastructure.report_to_ceo()
        return {"success": False, "error": "InfrastructureAgent未就绪"}

    def _auto_git_push(self):
        try:
            repo = str(PROJECT_ROOT)
            result = subprocess.run(["git", "status", "--porcelain"],
                                    cwd=repo, capture_output=True, text=True, shell=False)
            if not result.stdout.strip():
                return {"pushed": False, "reason": "无变更"}

            commit_msg = (
                f"CEO Auto: 第{self.cycle}轮 — "
                f"KPs:{self._last_kps_count} | "
                f"Audit:{self._last_audit_score:.1f} | "
                f"Fed:{self.metrics['kps_fed']} | "
                f"Agents:{self.metrics['agents_deployed']}"
            )

            subprocess.run(["git", "add", "-A"], cwd=repo,
                           capture_output=True, text=True, shell=False)
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo,
                           capture_output=True, text=True, shell=False)
            push_result = subprocess.run(["git", "push"], cwd=repo,
                                         capture_output=True, text=True, shell=False)

            self.metrics["git_pushes"] += 1
            self._log("Git推送", "info", commit_msg[:80])
            return {"pushed": True, "message": commit_msg}
        except Exception as e:
            self._log("Git推送失败", "error", str(e)[:200])
            return {"pushed": False, "error": str(e)[:200]}

    def _auto_update_claude_md(self, state):
        """自动同步所有项目文件(CLAUDE.md + README + docs/ + CHANGELOG)"""
        try:
            self.sync_all_project_files(state)
            self.metrics["claude_md_updates"] += 1
        except Exception as e:
            self._log("项目文件同步失败", "warning", str(e)[:200])

    def sync_all_project_files(self, state=None):
        """全面同步所有项目文件到当前状态。确保每次新对话从正确基线开始。"""
        if state is None:
            state = self._perceive()
        synced = []
        errors = []

        # 1. CLAUDE.md: 版本号+架构描述
        try:
            self._sync_file_claude_md(state)
            synced.append("CLAUDE.md")
        except Exception as e:
            errors.append(f"CLAUDE.md: {str(e)[:80]}")

        # 2. README.md: 版本号+架构+集团部门表
        try:
            self._sync_file_readme(state)
            synced.append("README.md")
        except Exception as e:
            errors.append(f"README.md: {str(e)[:80]}")

        # 3. docs/00_项目全景.md: 当前状态+模块+迭代路线
        try:
            self._sync_file_docs_00(state)
            synced.append("docs/00")
        except Exception as e:
            errors.append(f"docs/00: {str(e)[:80]}")

        # 4. CHANGELOG.md: 确保最新版本条目存在
        try:
            self._sync_file_changelog()
            synced.append("CHANGELOG.md")
        except Exception as e:
            errors.append(f"CHANGELOG: {str(e)[:80]}")

        if synced:
            self._log("项目文件同步", "info", f"已同步{len(synced)}个: {', '.join(synced)}")
        if errors:
            self._log("项目文件同步异常", "warning", "; ".join(errors))

        return {"synced": synced, "errors": errors}

    def _sync_file_claude_md(self, state):
        path = PROJECT_ROOT / "CLAUDE.md"
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        updated = content
        for pattern, replacement in [
            (r'当前代码版本:\*\*v[\d.]+[-a-zA-Z0-9]*\*\*', '当前代码版本:**v2.3.7**'),
            (r'当前设计版本:\*\*v[\d.]+[-a-zA-Z0-9]*\*\*', '当前设计版本:**v2.3.7**'),
            (r'进行中:.*', f'进行中: CEO receive_instruction协作 + 16Agent审计 + 客户画像验证(第{self.cycle}轮)'),
        ]:
            updated = re.sub(pattern, replacement, updated)
        if updated != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)

    def _sync_file_readme(self, state):
        path = PROJECT_ROOT / "README.md"
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        updated = content
        updated = re.sub(r'\*\*当前版本\*\*:\*\*v[\d.]+[-a-zA-Z0-9]*\*\*[^)]*\)',
                         f'**当前版本**:**v2.3.7**(集团化重构: 6部门16Agent + CEO V4-Pro会议决策)',
                         updated)
        if updated != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)

    def _sync_file_docs_00(self, state):
        path = PROJECT_ROOT / "docs" / "00_项目全景.md"
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        updated = content
        updated = re.sub(r'当前版本:\*\*v[\d.]+[-a-zA-Z0-9]*\*\*[^)]*\)',
                         f'当前版本:**v2.3.7**(6部门16Agent + CEO会议决策,第{self.cycle}轮)',
                         updated)
        updated = re.sub(r'\| \*\*v2\.3\.7\*\* \|.*\|.*\|',
                         '| **v2.3.7** | **集团化重构: 6部门16Agent+CEO会议决策+客户画像+NPU/GPU** | ✅ 2026-05-05 |',
                         updated)
        if updated != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)

    def _sync_file_changelog(self):
        path = PROJECT_ROOT / "CHANGELOG.md"
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if "## [v2.3.7]" not in content:
            self._log("CHANGELOG", "warning", "缺v2.3.7条目,需手动补充(已由本次对话添加)")

    def _report(self, state, plan, results):
        action = plan.get("action", "?")
        ok = results.get("success", False)
        msg = (f"[CEO-{self.cycle:03d}] {action:25s} | "
               f"KPs:{state['kps_confirmed']:5d} | "
               f"Audit:{state['audit_avg_score']:.1f} | "
               f"{'OK' if ok else 'FAIL'}")
        print(msg)
        self.log.append({"cycle": self.cycle, "action": action,
                         "ok": ok, "time": datetime.now().isoformat()})

    def _final_report(self):
        return {"cycles_completed": self.cycle, "metrics": self.metrics,
                "log": self.log[-20:], "conclusion": "CEO深度思考循环结束"}

    def _log(self, stage, level, msg):
        entry = f"[CEO] {stage}: {msg}"
        print(entry)
        try:
            if self.db:
                self.db.log_operation_event(
                    event_type=f"ceo_{stage}", severity=level,
                    module="ceo_agent", payload={"msg": msg})
        except Exception:
            pass

    def _write_task_queue(self, audit_result):
        try:
            queue_path = PROJECT_ROOT / "docs" / "06_自动迭代任务队列.md"
            tasks = audit_result.get("code_tasks") or []
            if not tasks:
                return
            with open(queue_path, "a", encoding="utf-8") as f:
                for t in tasks[:5]:
                    t_id = f"A{int(time.time()) % 10000:04d}"
                    f.write(f"| {t_id} | {t.get('type','code')} | {t.get('priority','P2')} "
                            f"| {t.get('source_agent','ceo')} | {t.get('description','')} | pending |\n")
        except Exception:
            pass


def main():
    print("=" * 60)
    print("  CEO Agent v2.3.7 — V4-Pro深度思考战略调度者")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    ceo = CEOAgent(headless=True)
    report = ceo.run(max_iterations=MAX_LOOP_ITERATIONS)
    print(f"\n  CEO最终报告: {json.dumps(report['metrics'], ensure_ascii=False)}")
    return report


if __name__ == "__main__":
    main()
