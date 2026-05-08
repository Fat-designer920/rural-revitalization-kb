"""
project_impact_analyzer.py - 政策变化对项目影响分析(超级王炸功能)
路径：scripts/project_impact_analyzer.py
版本：v2.3.7

王炸逻辑:新政策出来了→AI自动分析这个政策对用户正在做的项目有什么影响→
生成具体的"谁需要在什么时间前做什么事"的行动建议。

竞品做不到的:
- 北大法宝:只给原文,不分析影响
- 政策通:只推送,不关联项目
- ChatGPT:不懂具体项目和四川本地政策
- 我们:结构化的政策知识库+项目关联+15个角色视角=独此一家
"""
import json
from datetime import datetime, timedelta


class ProjectImpactAnalyzer(object):
    """项目影响分析器。王炸功能的核心引擎。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client

    def analyze_policy_impact(self, policy_text, user_projects):
        """分析一个政策文件对用户所有项目的影响。返回每个项目的影响评估。"""
        project_summaries = self._format_projects(user_projects)
        impacts = []

        for proj in user_projects[:10]:
            impact = self._ai_analyze_single_project(policy_text, proj)
            if impact:
                impact["project_name"] = proj.get("name", "")
                impacts.append(impact)

        return {
            "policy_summary": policy_text[:300],
            "analyzed_at": datetime.now().isoformat(),
            "total_projects": len(user_projects),
            "affected_projects": len([i for i in impacts if i.get("impact_level") != "none"]),
            "impacts": impacts,
            "urgent_actions": self._extract_urgent_actions(impacts),
        }

    def analyze_new_policy(self, new_policy_title, new_policy_content, county_context=None):
        """新政策发布时,分析对某个县所有已知项目类型的影响"""
        # 从知识库获取该县相关的项目类型
        project_types = [
            {"name": "全域土地综合整治项目", "type": "land_remediation"},
            {"name": "增减挂钩项目", "type": "increase_decrease_hook"},
            {"name": "高标准农田建设项目", "type": "high_standard_farmland"},
            {"name": "集体建设用地入市项目", "type": "collective_land_market"},
            {"name": "占补平衡项目", "type": "occupy_supplement_balance"},
            {"name": "宅基地改革项目", "type": "homestead_reform"},
            {"name": "生态修复治理项目", "type": "ecological_restoration"},
            {"name": "乡村产业运营项目", "type": "rural_industry"},
        ]

        results = []
        for pt in project_types:
            impact = self._ai_analyze_single_project(
                f"{new_policy_title}\n{new_policy_content[:1500]}",
                {"name": pt["name"], "type": pt["type"], "context": county_context or "四川省某县"}
            )
            if impact:
                impact["project_type"] = pt["name"]
                results.append(impact)

        return {
            "policy_title": new_policy_title,
            "county_context": county_context,
            "generated_at": datetime.now().isoformat(),
            "project_type_impacts": results,
            "overall_impact_summary": self._ai_summarize_all_impacts(results, new_policy_title),
        }

    def generate_alert_for_user(self, policy_change, user_id, user_projects):
        """为特定用户生成个性化政策预警"""
        analysis = self.analyze_policy_impact(policy_change, user_projects)
        affected = [i for i in analysis.get("impacts", []) if i.get("impact_level") in ("high", "critical")]

        return {
            "user_id": user_id,
            "alert_type": "policy_change",
            "severity": "critical" if len(affected) > 2 else "high" if affected else "low",
            "title": f"政策预警: {policy_change[:80]}",
            "affected_project_count": len(affected),
            "top_action": affected[0].get("required_action", "") if affected else "无需立即行动",
            "deadline": affected[0].get("deadline", "") if affected else "",
            "generated_at": datetime.now().isoformat(),
        }

    def _ai_analyze_single_project(self, policy_text, project):
        """AI分析单个项目受政策影响的程度"""
        system_prompt = f"""你是乡村振兴政策影响分析专家。新政策内容如下:

{policy_text[:2000]}

项目信息:
- 名称: {project.get('name','')}
- 类型: {project.get('type','')}
- 背景: {project.get('context','四川省某县')}

请分析这个新政策对这个项目的具体影响。用最保守、最实操的方式分析:

1. impact_level: 影响程度(none/low/medium/high/critical)
2. affected_aspects: 具体影响哪些方面(如审批流程/补偿标准/验收条件/资金渠道)
3. specific_change: 具体改变了什么(旧标准→新标准)
4. required_actions: 项目方需要采取的具体行动(按优先级排序)
5. deadline: 如果有时间限制,截止日期是什么
6. cost_impact: 对项目成本的预估影响(增加/减少/不变)
7. risk_if_ignore: 如果不采取行动会有什么风险
8. peer_reference: 四川省内类似项目的处理参考

返回JSON。措辞要具体,要有可操作性,不能空泛。"""

        try:
            resp = self.client.chat_with_json(
                system_prompt,
                f"请分析这个政策对{project.get('name','该项目')}的影响",
                temperature=0.1, model_override="deepseek-v4-pro",
                call_type="project_impact"
            )
            return resp.get("parsed_json") if isinstance(resp, dict) else {}
        except Exception:
            return {}

    def _ai_summarize_all_impacts(self, results, policy_title):
        """AI汇总所有项目类型的影响,生成高管摘要"""
        summaries = [f"{r.get('project_type','')}: {r.get('impact_level','?')}" for r in results[:8]]
        try:
            resp = self.client.chat_with_json(
                f"请汇总以下政策'{policy_title}'对各项目类型的影响分析,生成200字高管摘要:\n" + "\n".join(summaries),
                "请生成摘要",
                temperature=0.1, model_override="deepseek-v4-flash",
                call_type="impact_summary"
            )
            return resp.get("parsed_json") if isinstance(resp, dict) else {}
        except Exception:
            return {}

    def _format_projects(self, projects):
        return "\n".join([f"- {p.get('name','')}: {p.get('type','')}({p.get('context','')})"
                         for p in projects[:10]])

    def _extract_urgent_actions(self, impacts):
        """提取所有需要立即行动的事项"""
        urgent = []
        for imp in impacts:
            if imp.get("impact_level") in ("high", "critical"):
                for action in (imp.get("required_actions") or [])[:3]:
                    urgent.append({
                        "project": imp.get("project_name", ""),
                        "action": action,
                        "deadline": imp.get("deadline", ""),
                    })
        return sorted(urgent, key=lambda x: x.get("deadline", "9999"))
