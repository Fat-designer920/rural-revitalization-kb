"""
revenue_ops.py - 商业变现部操作中心(定价+包装+销售+收入优化)
路径：agents/revenue_ops.py
版本：v2.3.7-part4

月入20万的直接责任部门——不做PPT,只找钱在哪。
"""
from datetime import datetime

# 五档定价(来源: docs/07_商业战略.md)
PRICING_TIERS = {
    "basic":       {"price": 19.9,  "target_users": 2000, "monthly_target": 40000,  "label": "基础版"},
    "pro":         {"price": 99,    "target_users": 500,  "monthly_target": 50000,  "label": "专业版"},
    "expert":      {"price": 199,   "target_users": 200,  "monthly_target": 40000,  "label": "专家版"},
    "team":        {"price": 999,   "target_users": 30,   "monthly_target": 30000,  "label": "团队版"},
    "government":  {"price": 1667,  "target_users": 2,    "monthly_target": 3300,   "label": "县级版(年付折算月)"},
    "training":    {"price": 3980,  "target_users": 10,   "monthly_target": 40000,  "label": "操盘手训练营"},
}

MONTHLY_TARGET = 203000  # 月入20.3万目标


class RevenueOps(object):
    """商业变现部操作中心。定价+包装+销售+收入优化,月入20万的直接责任部门。"""

    def __init__(self, chief, members_dict, db=None, client=None):
        self.chief = chief
        self.members = members_dict
        self.db = db
        self.client = client

    def _get_agent(self, code):
        return self.members.get(code) if self.members else None

    def _call_agent(self, code, prompt):
        agent = self._get_agent(code)
        if not agent:
            return {"error": f"Agent {code} 未找到", "confidence": "low"}
        try:
            result = agent.think(prompt)
            return {
                "agent": agent.agent_name,
                "analysis": result.get("analysis", "")[:500],
                "confidence": result.get("confidence", "medium"),
            }
        except Exception as e:
            return {"agent": code, "error": str(e)[:200], "confidence": "low"}

    def analyze_pricing(self):
        """定价策略师分析当前定价模型。返回:各档价格弹性+竞品对比+调价建议。"""
        ps = self._get_agent("pricing_strategist")
        if not ps:
            return {"error": "pricing_strategist未加载", "tiers": PRICING_TIERS}

        prompt = (
            f"分析当前5档定价(¥19.9/99/199/999/20K年+¥3980培训):\n"
            f"1) 每档价格弹性估算(提价10%→用户流失多少)\n"
            f"2) 与目标(月入20.3万)的差距在哪一档\n"
            f"3) 调价建议(具体数字+置信度+执行时间)\n"
            f"4) 竞品对标:天天学农C+轮后的定价策略变化"
        )
        raw = self._call_agent("pricing_strategist", prompt)
        return {
            "tiers": PRICING_TIERS,
            "monthly_target": MONTHLY_TARGET,
            "analysis": raw.get("analysis", ""),
            "agent": "pricing_strategist",
            "timestamp": datetime.now().isoformat(),
        }

    def forecast_revenue(self):
        """收入优化师预测月收入:保守/基准/乐观三场景+关键假设+达标概率。"""
        ro = self._get_agent("revenue_optimizer")
        prompt = (
            f"预测未来3个月收入(目标¥{MONTHLY_TARGET}/月):\n"
            f"假设:基础版2000人/专业版500人/专家版200人/团队版30/政府2县/培训10人\n"
            f"输出:保守/基准/乐观三组数字+各档关键假设+最大风险因素+达标概率(%)"
        )
        raw = self._call_agent("revenue_optimizer", prompt) if ro else {"analysis": ""}
        return {
            "monthly_target": MONTHLY_TARGET,
            "scenarios": {
                "conservative": round(MONTHLY_TARGET * 0.5),
                "baseline": MONTHLY_TARGET,
                "optimistic": round(MONTHLY_TARGET * 1.5),
            },
            "analysis": raw.get("analysis", ""),
            "timestamp": datetime.now().isoformat(),
        }

    def calculate_unit_economics(self):
        """单位经济学:CAC/LTV/回本周期/毛利率 分档计算。"""
        ue = {}
        for key, tier in PRICING_TIERS.items():
            price = tier["price"]
            # 假设:CAC=首月价格的50%,毛利率=70%,月流失率=15%
            cac = round(price * 0.5, 1)
            gross_margin = 0.70
            churn = 0.15
            avg_lifetime_months = round(1.0 / churn, 1) if churn > 0 else 24
            ltv = round(price * avg_lifetime_months * gross_margin, 1)
            payback_months = round(cac / (price * gross_margin), 1) if price > 0 else 999
            ue[key] = {
                "label": tier["label"], "price": price,
                "cac": cac, "gross_margin": gross_margin,
                "avg_lifetime_months": avg_lifetime_months, "ltv": ltv,
                "payback_months": payback_months,
                "ltv_cac_ratio": round(ltv / cac, 1) if cac > 0 else 0,
            }
        return {"unit_economics": ue, "timestamp": datetime.now().isoformat()}

    def analyze_customer_feedback(self):
        """从QA反馈提取付费意愿信号:热力图+功能需求排名+流失风险预警。"""
        fa = self._get_agent("feedback_analyzer")
        prompt = (
            "分析当前客户反馈数据,提取:\n"
            "1) 付费意愿信号(什么让用户从'不付'变成'愿意付')\n"
            "2) 功能需求排名(缺什么功能导致不续费)\n"
            "3) 流失风险预警(哪些用户在流失边缘,按收入影响排序)\n"
            "4) NPS各档分布+改进建议"
        )
        raw = self._call_agent("feedback_analyzer", prompt) if fa else {"analysis": ""}
        return {
            "analysis": raw.get("analysis", ""),
            "agent": "feedback_analyzer",
            "timestamp": datetime.now().isoformat(),
        }

    def package_product(self, kp_bundle, package_type):
        """将KP打包成可售卖产品。package_type: policy_brief/strategy_template/financing_guide/training_kit."""
        cp = self._get_agent("content_packager")
        if not cp:
            return {"error": "content_packager未加载"}

        tier_map = {
            "policy_brief": ("basic", 19.9, "政策速查卡"),
            "strategy_template": ("pro", 99, "策划方案模板"),
            "financing_guide": ("expert", 199, "融资路径指南"),
            "training_kit": ("training", 3980, "培训课件"),
        }
        tier_info = tier_map.get(package_type, ("pro", 99, "通用产品"))

        prompt = (
            f"将以下KP打包为'{tier_info[2]}'(定价¥{tier_info[1]}/{tier_info[0]}档):\n"
            f"KP标题: {kp_bundle.get('title', '未命名')}\n"
            f"KP数量: {len(kp_bundle.get('items', []))}条\n"
            f"要求:目标客户定位+产品描述+定价理由+预期月销量+差异化卖点"
        )
        raw = self._call_agent("content_packager", prompt)
        return {
            "package_type": package_type,
            "tier": tier_info[0], "price": tier_info[1], "label": tier_info[2],
            "kp_count": len(kp_bundle.get("items", [])),
            "analysis": raw.get("analysis", ""),
            "timestamp": datetime.now().isoformat(),
        }

    def weekly_revenue_report(self):
        """周度收入报告:预测+差距分析+行动建议,对标¥203K/月目标。"""
        chief = self.chief
        if not chief:
            return {"error": "Chief未加载"}

        # 汇总各成员KPI
        member_summary = []
        for code in ["pricing_strategist", "content_packager", "sales_page_gen", "feedback_analyzer"]:
            agent = self._get_agent(code)
            if agent:
                member_summary.append({
                    "name": agent.agent_name, "code": code,
                    "calls": getattr(agent, "_call_count", 0),
                })

        prompt = (
            f"周度收入报告(目标¥{MONTHLY_TARGET}/月=¥{round(MONTHLY_TARGET/4.33)}/周):\n"
            f"1) 本周预估收入\n2) 与目标差距\n3) 本周最大收入机会\n4) 本周最大风险\n"
            f"5) 下周3个具体行动(每个标注预期收入影响+置信度)"
        )
        raw = self._call_agent("revenue_optimizer", prompt)

        return {
            "week": datetime.now().strftime("%Y-W%W"),
            "monthly_target": MONTHLY_TARGET,
            "weekly_target": round(MONTHLY_TARGET / 4.33),
            "analysis": raw.get("analysis", ""),
            "member_summary": member_summary,
            "timestamp": datetime.now().isoformat(),
        }

    def department_status(self):
        """一键看板:KPI达成率+转化漏斗+定价健康度+部门状态。"""
        ue = self.calculate_unit_economics()
        tiers_health = {}
        for key, data in ue.get("unit_economics", {}).items():
            tiers_health[key] = {
                "label": data["label"],
                "ltv_cac": data["ltv_cac_ratio"],
                "payback": data["payback_months"],
                "healthy": data["ltv_cac_ratio"] >= 3.0,
            }

        chief_info = {}
        if self.chief:
            try:
                chief_info = self.chief.daily_standup() if hasattr(self.chief, "daily_standup") else {}
            except Exception:
                chief_info = {"error": "daily_standup调用失败"}

        member_count = len(self.members) if self.members else 0
        return {
            "department": "商业变现部",
            "mission": "把知识变成钱,月入20万",
            "monthly_target": MONTHLY_TARGET,
            "chief": self.chief.agent_name if self.chief else "未设置",
            "member_count": member_count,
            "member_codes": list(self.members.keys()) if self.members else [],
            "tiers_health": tiers_health,
            "chief_standup": chief_info,
            "conversion_funnel": {
                "visitor_to_trial": "待采集",
                "trial_to_basic": "待采集",
                "basic_to_pro_upgrade": "≥15%目标",
                "pro_to_expert_upgrade": "待采集",
            },
            "kpi_status": {
                "basic_conversion": "≥8%目标",
                "churn_rate_target": "<15%/月",
                "arpu_target": "≥¥89中位数",
            },
            "timestamp": datetime.now().isoformat(),
        }


def get_revenue_ops(db=None, client=None):
    """工厂函数:从agent_orchestra加载全部Agent,构建RevenueOps实例。"""
    from agents.agent_orchestra import build_all_agents

    result = build_all_agents(client=client, db=db)
    all_agents = result["agents"]
    rev_dept = result["departments"].get("revenue", {})
    chief_code = rev_dept.get("chief", "revenue_optimizer")
    member_codes = rev_dept.get("members", [])

    agent_lookup = {a.agent_code: a for a in all_agents}
    chief = agent_lookup.get(chief_code)
    members_dict = {code: agent_lookup[code] for code in member_codes if code in agent_lookup}
    if chief:
        members_dict[chief_code] = chief

    return RevenueOps(chief, members_dict, db=db, client=client)
