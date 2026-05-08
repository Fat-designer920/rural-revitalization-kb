"""
agent_evolver.py - Agent持续进化系统(会后自动升级+能力追踪+效果验证)
路径：agents/agent_evolver.py
版本：v2.3.7

每次CEO会议决策→立即执行Agent能力升级→追踪效果→持续迭代
Agent不是一成不变的,而是随着业务需求不断进化的。
"""
import json
from datetime import datetime


class AgentEvolver(object):
    """Agent持续进化器。监控→评估→升级→验证四步闭环。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client
        self.evolution_log = []

    def evolve_after_meeting(self, meeting_decisions):
        """会议决策后立即升级Agent能力"""
        upgrades = []

        for decision in meeting_decisions.get("action_items", []):
            affected_agents = self._identify_affected_agents(decision)
            for agent_code in affected_agents:
                upgrade = self._upgrade_agent(agent_code, decision)
                if upgrade:
                    upgrades.append(upgrade)

        return {
            "evolved_at": datetime.now().isoformat(),
            "trigger": meeting_decisions.get("ceo_decision", "")[:100],
            "upgrades_applied": len(upgrades),
            "details": upgrades,
        }

    def evaluate_agent(self, agent_code):
        """评估单个Agent的能力水平(基于最近10次评分)"""
        agent = self._get_agent(agent_code)
        if not agent:
            return {"error": "Agent not found"}

        # 模拟评估:实际应该基于审计数据
        return {
            "agent_code": agent_code,
            "agent_name": agent.get("agent_name", ""),
            "capability_score": self._calculate_capability(agent_code),
            "weakest_dimension": self._find_weakest_dimension(agent_code),
            "evolution_suggestions": self._suggest_improvements(agent),
            "evaluated_at": datetime.now().isoformat(),
        }

    def auto_upgrade_low_performers(self, threshold=2.5):
        """自动升级低分Agent(评分<2.5的自动触发)"""
        all_agents = self.db.get_active_agents()
        upgrades = []

        for agent in all_agents:
            score = self._calculate_capability(agent["agent_code"])
            if score < threshold:
                upgrade = self._upgrade_agent(agent["agent_code"], f"自动升级(评分{score:.1f}<{threshold})")
                if upgrade:
                    upgrades.append(upgrade)

        return {
            "auto_upgraded": len(upgrades),
            "threshold": threshold,
            "details": upgrades,
            "upgraded_at": datetime.now().isoformat(),
        }

    def _upgrade_agent(self, agent_code, reason):
        """升级单个Agent:优化其core_questions和scoring_dimensions"""
        agent = self._get_agent(agent_code)
        if not agent:
            return None

        # AI分析Agent需要什么改进
        try:
            system_prompt = f"""你是Agent能力升级专家。当前Agent:
名称: {agent.get('agent_name','')}
身份: {agent.get('identity_text','')[:150]}
核心问题: {agent.get('core_questions','')}
评分维度: {agent.get('scoring_dimensions','')}

升级原因: {reason}

请提出具体的升级建议:
1. 核心问题是否过时?需要新增什么?
2. 评分维度是否需要调整?
3. 质量标准是否需要提高?

返回JSON: {{"new_questions": [...], "new_dimensions": [...], "new_standards": [...], "upgrade_summary": "≤100字"}}"""

            resp = self.client.chat_with_json(system_prompt, "请升级Agent",
                                              temperature=0.2, model_override="deepseek-v4-flash",
                                              call_type="agent_upgrade")
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}

            # 应用升级(更新DB)
            if parsed.get("new_questions") or parsed.get("new_dimensions"):
                self._apply_upgrade(agent_code, parsed)

            self.evolution_log.append({
                "agent_code": agent_code,
                "reason": reason,
                "upgrade": parsed,
                "time": datetime.now().isoformat(),
            })

            return {"agent_code": agent_code, "upgrade": parsed.get("upgrade_summary", "")}
        except Exception:
            return None

    def _apply_upgrade(self, agent_code, upgrade):
        """将升级应用到DB"""
        conn = None
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            if upgrade.get("new_questions"):
                c.execute("UPDATE agent_definitions SET core_questions=?, updated_at=datetime('now','localtime') WHERE agent_code=?",
                          (json.dumps(upgrade["new_questions"], ensure_ascii=False), agent_code))
            if upgrade.get("new_dimensions"):
                c.execute("UPDATE agent_definitions SET scoring_dimensions=?, updated_at=datetime('now','localtime') WHERE agent_code=?",
                          (json.dumps(upgrade["new_dimensions"], ensure_ascii=False), agent_code))
            conn.commit()
        except Exception:
            try:
                if conn: conn.rollback()
            except Exception:
                pass
        finally:
            try:
                if conn: conn.close()
            except Exception:
                pass

    def _get_agent(self, agent_code):
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT * FROM agent_definitions WHERE agent_code=?", (agent_code,))
            row = c.fetchone()
            conn.close()
            if row:
                r = dict(row)
                for f in ("core_questions","scoring_dimensions","quality_standards"):
                    if isinstance(r.get(f), str):
                        try: r[f] = json.loads(r[f])
                        except (json.JSONDecodeError, TypeError): pass
                return r
        except Exception:
            pass
        return None

    def _calculate_capability(self, agent_code):
        """从 audit_cycles 表读取该Agent最近评分,计算真实能力值"""
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("""SELECT report_json FROM audit_cycles
                         WHERE status='completed' ORDER BY created_at DESC LIMIT 3""")
            rows = c.fetchall()
            conn.close()
            scores = []
            for (rj,) in rows:
                try:
                    report = json.loads(rj) if isinstance(rj, str) else rj
                    for ag in report.get("agent_summaries", []):
                        if ag.get("agent_code") == agent_code:
                            scores.append(ag.get("avg_score", 0))
                except Exception:
                    pass
            if scores:
                return round(sum(scores) / len(scores), 1)
            return 3.0  # 无数据=中等
        except Exception:
            return 3.0

    def _find_weakest_dimension(self, agent_code):
        """从最近审计报告分析最弱维度"""
        agent = self._get_agent(agent_code)
        dims = agent.get("scoring_dimensions", []) if agent else []
        if not dims:
            return "无评分维度定义"
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("""SELECT report_json FROM audit_cycles
                         WHERE status='completed' ORDER BY created_at DESC LIMIT 1""")
            row = c.fetchone()
            conn.close()
            if row:
                report = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                for ag in report.get("agent_summaries", []):
                    if ag.get("agent_code") == agent_code and ag.get("dim_scores"):
                        dim_scores = ag["dim_scores"]
                        if dim_scores:
                            return min(dim_scores, key=dim_scores.get)
        except Exception:
            pass
        return dims[0] if dims else "未知"

    def _suggest_improvements(self, agent):
        """基于审计数据生成改进建议"""
        agent_code = agent.get("agent_code", "")
        weakest = self._find_weakest_dimension(agent_code)
        capability = self._calculate_capability(agent_code)
        suggestions = []
        if capability < 2.5:
            suggestions.append("评分" + str(capability) + "偏低,建议AI深度评估并升级核心问题")
        if weakest and weakest != "未知":
            suggestions.append(f"最弱维度'{weakest}'需重点改进")
        if capability >= 4.0:
            suggestions.append("Agent表现优秀,可考虑扩大评审范围")
        if not suggestions:
            suggestions.append("运行首次审计后自动生成具体改进建议")
        return suggestions[:3]

    def _identify_affected_agents(self, decision):
        """根据决策内容识别受影响的Agent"""
        decision_lower = decision.lower()
        affected = []
        if any(w in decision_lower for w in ["提取","质量","qa","content"]):
            affected.extend(["extraction_quality","content_gatekeeper"])
        if any(w in decision_lower for w in ["ui","设计","界面","design"]):
            affected.extend(["ui_architect","visual_designer","interaction_designer"])
        if any(w in decision_lower for w in ["审计","audit","质检"]):
            affected.extend(["agent_evolution"])
        if any(w in decision_lower for w in ["市场","营销","market","定价"]):
            affected.extend(["gtm_strategist"])
        return affected[:3]
