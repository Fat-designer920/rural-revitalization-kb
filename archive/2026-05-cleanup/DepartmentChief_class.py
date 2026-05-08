class DepartmentChief(StrategyAgent):
    """部门长 — 管理一个部门的所有Agent,驱动部门运转。
    继承StrategyAgent(V4-Pro),拥有部门管理能力:
    - set_department: 指定部门key、使命和成员列表
    - list_members: 列出本部门所有成员
    - hold_dept_meeting: 召集成员开部门会议
    - assign_task: 分派任务给指定成员
    - daily_standup: 每日站会检查部门状态
    - collect_kpis: 采集本部门KPI数据
    - report_to_ceo: 向CEO汇报部门状态
    """

    def __init__(self, agent_code, agent_name, identity_text,
                 core_questions, quality_standards, scoring_dimensions,
                 client=None, db=None):
        super(DepartmentChief, self).__init__(
            agent_code, agent_name, identity_text,
            core_questions, quality_standards, scoring_dimensions,
            client, db,
        )
        self._members = []
        self._dept_key = None
        self._dept_mission = ""
        self._dept_kpi = {}

    def set_department(self, dept_key, mission, members):
        """设置部门: 指定部门key、使命和成员列表"""
        self._dept_key = dept_key
        self._dept_mission = mission
        self._members = members

    def list_members(self):
        """列出本部门所有成员(name/code/type/calls)"""
        return [{
            "name": m.agent_name, "code": m.agent_code,
            "type": getattr(m, "agent_type", "?"),
            "calls": getattr(m, "_call_count", 0),
        } for m in self._members]

    def hold_dept_meeting(self, topic, client=None):
        """召集本部门Agent开部门会议(简化版,不走CEO七步协议)。
        每个成员用think()发表意见,部门长汇总后决策。"""
        opinions = []
        for m in self._members:
            try:
                result = m.think(
                    f"[{self._dept_key}部门会议,主持:{self.agent_name}] 议题:{topic}"
                )
                opinions.append({
                    "agent": m.agent_name,
                    "opinion": result.get("analysis", "")[:300],
                    "confidence": result.get("confidence", "medium"),
                })
            except Exception:
                opinions.append({
                    "agent": m.agent_name,
                    "opinion": "[无法参与讨论]",
                    "confidence": "low",
                })
        # 部门长汇总决策
        synopsis = (f"[{self.agent_name}]综合{len(opinions)}条意见:"
                    f"已听取部门内各Agent观点,待形成最终决策。")
        return {
            "topic": topic, "dept": self._dept_key,
            "opinions": opinions, "decision": synopsis,
        }

    def assign_task(self, agent_code, task_description):
        """分派任务给指定成员。让该成员think()任务并返回响应。"""
        target = None
        for m in self._members:
            if m.agent_code == agent_code:
                target = m
                break
        if not target:
            return {"error": f"成员{agent_code}不在本部门", "dept": self._dept_key}
        try:
            result = target.think(
                f"[任务分派自{self.agent_name}] {task_description}"
            )
            return {
                "assigned_to": agent_code, "task": task_description,
                "response": result.get("analysis", "")[:300],
            }
        except Exception as e:
            return {"assigned_to": agent_code, "error": str(e)[:200]}

    def daily_standup(self):
        """每日站会: 检查部门状态,输出简报"""
        return {
            "dept": self._dept_key, "chief": self.agent_name,
            "member_count": len(self._members),
            "members": [m.agent_name for m in self._members],
            "total_calls": sum(getattr(m, "_call_count", 0) for m in self._members),
            "total_cost": round(sum(getattr(m, "_total_cost", 0) for m in self._members), 4),
            "mission": self._dept_mission,
        }

    def collect_kpis(self, db=None):
        """采集本部门KPI数据(含DB查询)"""
        kpis = {
            "dept": self._dept_key,
            "member_count": len(self._members),
            "total_calls": sum(getattr(m, "_call_count", 0) for m in self._members),
            "total_cost": round(sum(getattr(m, "_total_cost", 0) for m in self._members), 4),
        }
        if db:
            try:
                cursor = db.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed'"
                )
                kpis["confirmed_kps"] = cursor.fetchone()[0]
            except Exception:
                pass
        self._dept_kpi = kpis
        return kpis

    def report_to_ceo(self):
        """向CEO汇报: 部门状态+关键指标+需要CEO决策的事项"""
        return {
            "dept": self._dept_key,
            "mission": self._dept_mission,
            "chief": self.agent_name,
            "member_count": len(self._members),
            "members": [m.agent_name for m in self._members],
            "kpis": self._dept_kpi,
            "needs_ceo_attention": [],
        }
