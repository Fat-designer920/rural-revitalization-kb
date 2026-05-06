"""
evolution_ops.py - 演进层操作中心(Agent自我进化+持续学习+竞品监控+内容保鲜)
路径：agents/evolution_ops.py
版本：v2.3.7-part4
"""
import json, traceback
from datetime import datetime


class EvolutionOps(object):
    """演进层操作中心。整合4个演进Agent + AgentEvolver + AgentVerifier + PromptOptimizer，
    对外提供统一的周度演进循环入口。"""

    def __init__(self, evolution_agents_dict, db=None, client=None):
        self.evolution_agents = evolution_agents_dict  # {agent_code: BaseAgent}
        self.db = db
        self.client = client
        self._evolver = None
        self._verifier = None
        self._prompt_optimizer = None
        self._orchestra_agents = None
        self.evolution_history = []
        self.cycle_count = 0

    def _lazy_init(self):
        if self._evolver is None:
            from agents.agent_evolver import AgentEvolver
            self._evolver = AgentEvolver(db=self.db, client=self.client)
        if self._verifier is None:
            from agents.agent_verifier import AgentVerifier
            self._verifier = AgentVerifier(client=self.client, db=self.db)
        if self._prompt_optimizer is None:
            from agents.prompt_optimizer import PromptOptimizer
            self._prompt_optimizer = PromptOptimizer(db=self.db, client=self.client)

    def set_orchestra_agents(self, agents_list):
        """注入全部Agent列表(来自CEO._orchestra), 用于批量评估和升级"""
        self._orchestra_agents = agents_list

    def weekly_evolution_cycle(self):
        """周度演进循环: 评估→升级→优化Prompt→竞品情报→技术扫描→报告"""
        self._lazy_init()
        self.cycle_count += 1
        steps = []

        # 1. 评估所有Agent (AgentVerifier 4项测试)
        eval_result = self.evaluate_all_agents()
        steps.append("评估: {}/{} 通过".format(
            eval_result.get("passed", 0), eval_result.get("total", 0)))

        # 2. 升级低分Agent (AgentEvolver, threshold=3.0)
        upgrade_result = self.upgrade_low_performers(threshold=3.0)
        steps.append("升级: {} 个".format(upgrade_result.get("auto_upgraded", 0)))

        # 3. 优化Prompt (PromptOptimizer)
        try:
            prompt_result = self._prompt_optimizer.optimize_iteration()
            steps.append("Prompt: {} 处修改建议".format(
                prompt_result.get("prompts_modified", 0)))
        except Exception:
            prompt_result = {"success": False, "error": traceback.format_exc()[-200:]}
            steps.append("Prompt: 异常")

        # 4. 竞品情报更新 (competitive_intelligence Agent)
        comp_result = self.competitive_brief()
        steps.append("竞品: {} 条更新".format(comp_result.get("updates_found", 0)))

        # 5. 技术趋势扫描 (continuous_learner Agent)
        tech_result = self.tech_scan_brief()
        steps.append("技术: {} 条趋势".format(tech_result.get("trends_found", 0)))

        # 6. 生成演进月报
        full_report = self.evolution_report()
        steps.append("报告: 已生成")

        self.evolution_history.append({
            "cycle": self.cycle_count,
            "time": datetime.now().isoformat(),
            "eval": eval_result,
            "upgrade": upgrade_result,
            "prompt": prompt_result,
            "competitive": comp_result,
            "tech": tech_result,
            "summary": full_report.get("summary", ""),
        })

        return {
            "success": True,
            "cycle": self.cycle_count,
            "summary": " | ".join(steps),
            "details": {
                "evaluation": eval_result,
                "upgrades": upgrade_result,
                "prompt_optimization": prompt_result,
                "competitive_intel": comp_result,
                "tech_scan": tech_result,
                "evolution_report": full_report,
            },
            "history_entry_index": len(self.evolution_history) - 1,
        }

    def evaluate_all_agents(self):
        """用AgentVerifier验证全部Agent, 返回评分表。
        若Agent无AI客户端则返回no_client标记,不阻塞流程。"""
        agents = self._orchestra_agents or []
        if not agents:
            return {"total": 0, "passed": 0, "failed": 0,
                    "pass_rate": 0, "error": "无Agent列表, 请先调用set_orchestra_agents()"}

        try:
            result = self._verifier.verify_all(agents)
            return result
        except Exception as e:
            return {"total": len(agents), "passed": 0, "failed": len(agents),
                    "pass_rate": 0, "error": str(e)[:200],
                    "details": [], "failed_agents": [a.agent_name for a in agents]}

    def upgrade_low_performers(self, threshold=3.0):
        """自动升级评分<threshold的Agent。内部调用AgentEvolver。"""
        self._lazy_init()
        try:
            return self._evolver.auto_upgrade_low_performers(threshold=threshold)
        except Exception as e:
            return {"auto_upgraded": 0, "threshold": threshold,
                    "details": [], "error": str(e)[:200]}

    def competitive_brief(self):
        """竞品情报简报: 调度competitive_intelligence Agent执行快速扫描。
        返回监控对象覆盖情况和更新计数。"""
        agent = self.evolution_agents.get("competitive_intelligence")
        updates_found = 0
        agent_thought = None

        if agent and agent.client:
            try:
                context = {
                    "task": "竞品情报周度扫描",
                    "from_evolution_ops": True,
                    "cycle": self.cycle_count,
                }
                agent_thought = agent.think(context)
                updates_found = 1 if agent_thought else 0
            except Exception:
                pass

        return {
            "updates_found": updates_found,
            "monitored_competitors": ["天天学农", "齐鲁农云", "湖南用地宝", "快手三农"],
            "agent_responded": agent_thought is not None,
            "brief_at": datetime.now().isoformat(),
        }

    def tech_scan_brief(self):
        """技术趋势扫描: 调度continuous_learner Agent执行前沿扫描。
        返回扫描领域覆盖情况和趋势计数。"""
        agent = self.evolution_agents.get("continuous_learner")
        trends_found = 0
        agent_thought = None

        if agent and agent.client:
            try:
                context = {
                    "task": "技术趋势周度扫描",
                    "from_evolution_ops": True,
                    "cycle": self.cycle_count,
                }
                agent_thought = agent.think(context)
                trends_found = 1 if agent_thought else 0
            except Exception:
                pass

        return {
            "trends_found": trends_found,
            "scan_areas": ["AI前沿", "工具生态", "行业知识", "商业方法"],
            "agent_responded": agent_thought is not None,
            "brief_at": datetime.now().isoformat(),
        }

    def evolution_report(self):
        """演进月报: 汇总Agent评分变化+升级记录+竞品变化+技术趋势+改进建议。"""
        evolution_agent_names = [a.agent_name
                                 for a in self.evolution_agents.values()]

        if not self.evolution_history:
            return {
                "summary": "首次运行,尚未积累历史数据",
                "evolution_agents_active": evolution_agent_names,
                "cycle_count": self.cycle_count,
                "generated_at": datetime.now().isoformat(),
                "recommendations": ["建议运行至少1个完整周度循环后评估趋势"],
            }

        last = self.evolution_history[-1]
        eval_data = last.get("eval", {})
        upgrade_data = last.get("upgrade", {})

        parts = []
        pr = eval_data.get("pass_rate", "?")
        parts.append("通过率{}%".format(pr))
        if upgrade_data.get("auto_upgraded", 0) > 0:
            parts.append("升级{}个Agent".format(upgrade_data["auto_upgraded"]))
        if not parts:
            parts.append("监控中")

        return {
            "summary": "; ".join(parts),
            "evolution_agents_active": evolution_agent_names,
            "cycle_count": self.cycle_count,
            "generated_at": datetime.now().isoformat(),
            "recommendations": self._generate_recommendations(),
        }

    def _generate_recommendations(self):
        recs = []
        if not self.evolution_history:
            return ["建议运行至少1个完整周度循环后评估"]

        last = self.evolution_history[-1]
        eval_data = last.get("eval", {})
        fail_count = eval_data.get("failed", 0)
        if fail_count > 0:
            failed_names = eval_data.get("failed_agents", [])
            names_str = ", ".join(failed_names[:5])
            recs.append("{}个Agent未通过验证({}), 建议优先升级并重测".format(
                fail_count, names_str))

        pass_rate = eval_data.get("pass_rate", 100)
        upgrade_data = last.get("upgrade", {})
        if upgrade_data.get("auto_upgraded", 0) == 0 and pass_rate < 80:
            recs.append("通过率{}%偏低但无自动升级触发, 建议检查阈值".format(pass_rate))

        prompt_data = last.get("prompt", {})
        if prompt_data.get("prompts_modified", 0) == 0 and pass_rate < 90:
            recs.append("低通过率但Prompt优化建议为空, 建议运行AuditEngine累积分后重试")

        if not recs:
            recs.append("系统运行良好, Agent通过率{}%, 建议持续监控".format(pass_rate))
        return recs


def build_evolution_ops_from_ceo(ceo_agent):
    """从CEO实例构建EvolutionOps(便捷工厂函数)。
    自动提取evolution agents + orchestra agents + db + client。"""
    from agents.evolution_agents import build_evolution_agents

    evolution_list = build_evolution_agents(client=ceo_agent.client, db=ceo_agent.db)
    evolution_dict = {a.agent_code: a for a in evolution_list}

    ops = EvolutionOps(evolution_dict, db=ceo_agent.db, client=ceo_agent.client)
    if ceo_agent._orchestra:
        ops.set_orchestra_agents(ceo_agent._orchestra)

    return ops
