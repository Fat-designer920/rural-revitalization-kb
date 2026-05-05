"""
market_intel_agent.py - 市场情报Agent(动态监控竞品/政策/市场→实时报告CEO)
路径：agents/market_intel_agent.py
版本：v2.3.7

市场变化很快。本Agent持续监控:竞品动态/政策变化/市场趋势/用户需求变化。
每周自动生成市场情报简报,发现重大变化立即预警CEO。
"""
import json
from datetime import datetime, timedelta


class MarketIntelAgent(object):
    """市场情报Agent。监控四维:竞品/政策/市场/用户,动态报告CEO。"""

    MONITOR_TOPICS = {
        "competitors": [
            "天天学农 乡村振兴 新功能",
            "北大法宝 政策查询 定价",
            "阿里AI特派员 乡村振兴",
            "齐鲁农云 山东 农业农村",
            "湖南乡村振兴用地宝",
        ],
        "policy_sichuan": [
            "四川 全域土地综合整治 2026",
            "四川 增减挂钩 政策",
            "四川 高标准农田 2026",
            "四川 集体建设用地入市",
            "四川 宅基地改革",
        ],
        "market_trends": [
            "乡村振兴 知识付费 市场",
            "农业AI 应用 2026",
            "乡村干部 数字化工具",
            "农村 小程序 知识服务",
        ],
        "user_needs": [
            "乡镇干部 最需要 什么工具",
            "村支书 政策 怎么查",
            "土地整治 项目 咨询 需求",
            "乡村振兴 培训 需求 四川",
        ],
    }

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client
        self.last_report_time = None
        self.alert_thresholds = {
            "new_competitor": True,      # 新竞品出现→立即预警
            "policy_change": True,       # 重大政策变化→立即预警
            "market_shift": True,        # 市场重大转变→立即预警
            "pricing_change": True,      # 竞品价格变化→立即预警
        }

    def generate_weekly_brief(self):
        """生成每周市场情报简报→提交CEO"""
        brief = {
            "generated_at": datetime.now().isoformat(),
            "week": datetime.now().strftime("%Y-W%V"),
            "sections": {}
        }

        for category, topics in self.MONITOR_TOPICS.items():
            section = self._analyze_category(category, topics[:3])
            brief["sections"][category] = section

        brief["ceo_recommendations"] = self._generate_ceo_recommendations(brief)
        brief["alerts"] = self._check_alerts(brief)

        self.last_report_time = datetime.now()
        return brief

    def check_urgent_alerts(self):
        """检查是否有需要立即预警CEO的重大变化"""
        alerts = []

        # 这里由Claude Code的WebSearch工具动态提供搜索能力
        # 本模块负责分析框架和决策逻辑

        return alerts

    def _analyze_category(self, category, topics):
        """AI分析某一类情报(由WebSearch提供原始数据,AI负责分析)"""
        analysis_prompt = f"""你是市场情报分析专家。请分析乡村振兴知识服务市场的'{category}'领域。

需要关注:
- 有什么新变化?
- 对我们的产品有什么影响?
- 我们需要采取什么行动?

请用JSON返回分析结果:
{{
  "key_changes": ["变化1", "变化2"],
  "impact_level": "high/medium/low",
  "our_response": "建议的应对策略",
  "monitoring_priority": "继续保持/加大监控/降低频率"
}}"""

        try:
            resp = self.client.chat_with_json(
                analysis_prompt,
                f"请分析{category}领域的最新动态: {', '.join(topics)}",
                temperature=0.1, model_override="deepseek-v4-flash",
                call_type="market_intel"
            )
            return resp.get("parsed_json") if isinstance(resp, dict) else {}
        except Exception:
            return {"key_changes": [], "impact_level": "unknown"}

    def _generate_ceo_recommendations(self, brief):
        """基于情报生成CEO行动建议"""
        high_impacts = []
        for cat, section in brief.get("sections", {}).items():
            if isinstance(section, dict) and section.get("impact_level") == "high":
                high_impacts.append(cat)

        recommendations = []
        if "competitors" in high_impacts:
            recommendations.append("竞品有重大动作,建议CEO48小时内评估并调整策略")
        if "policy_sichuan" in high_impacts:
            recommendations.append("四川政策有变化,建议立即更新知识库并通知相关用户")
        if "market_trends" in high_impacts:
            recommendations.append("市场趋势转变,建议重新评估产品定位和定价策略")

        return recommendations

    def _check_alerts(self, brief):
        """检查是否需要触发即时预警"""
        alerts = []
        for cat, section in brief.get("sections", {}).items():
            if isinstance(section, dict) and section.get("impact_level") == "high":
                alerts.append({
                    "category": cat,
                    "severity": "high",
                    "message": f"{cat}领域有重大变化需CEO关注",
                    "timestamp": datetime.now().isoformat(),
                })
        return alerts


class CompetitiveAnalyzer(object):
    """竞品深度分析器。定期扫描竞品,更新竞品数据库,识别威胁和机会。"""

    COMPETITORS = [
        {"name": "天天学农", "type": "training", "threat_level": "medium",
         "strength": "8万+课程,3000+专家,C+轮融资", "weakness": "偏培训,不深挖政策解读"},
        {"name": "北大法宝", "type": "policy_query", "threat_level": "low",
         "strength": "政策原文库最全,政府机构标配", "weakness": "只有原文,无解读无项目关联"},
        {"name": "阿里AI特派员", "type": "tech_platform", "threat_level": "medium",
         "strength": "阿里技术+县域政府关系", "weakness": "通用型,不深耕乡村振兴垂直领域"},
        {"name": "齐鲁农云", "type": "gov_platform", "threat_level": "low",
         "strength": "山东省级平台,29亿条数据", "weakness": "仅山东,不跨省"},
        {"name": "政策通/其他小程序", "type": "policy_push", "threat_level": "low",
         "strength": "政策推送及时", "weakness": "无深度解读,无项目关联,无角色视角"},
    ]

    def __init__(self, client=None):
        self.client = client

    def analyze_threats(self):
        """AI分析竞品威胁等级和应对策略"""
        competitor_text = "\n".join([
            f"{c['name']}({c['type']}): 优势={c['strength']}, 劣势={c['weakness']}, 威胁={c['threat_level']}"
            for c in self.COMPETITORS
        ])

        try:
            resp = self.client.chat_with_json(
                f"你是竞品分析专家。请分析以下竞品对我们的威胁程度和我们的差异化应对策略:\n{competitor_text}",
                "请分析竞品威胁",
                temperature=0.2, model_override="deepseek-v4-flash",
                call_type="competitor_analysis"
            )
            return resp.get("parsed_json") if isinstance(resp, dict) else {}
        except Exception:
            return {}
