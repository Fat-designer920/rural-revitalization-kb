"""
compliance_checker.py - AI政策合规检查引擎(政府端核心卖点)
路径：scripts/compliance_checker.py
版本：v2.3.7

政府客户核心痛点:怕踩红线被追责。本模块用AI自动检查项目方案的政策合规性,
给出具体风险点和同类项目的审批先例。这是¥20万/年政府产品的核心功能。
"""
import json
from datetime import datetime


class ComplianceChecker(object):
    """AI政策合规检查器。输入项目方案→AI逐条检查政策合规性→输出风险报告。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client

    def check_project(self, project_description, project_type="land_remediation"):
        """检查单个项目的政策合规性。返回合规报告。"""
        # 获取相关知识点作为检查依据
        kps = self._fetch_relevant_policies(project_type, limit=30)
        kp_text = self._format_kps(kps)

        report = self._ai_compliance_check(project_description, kp_text, project_type)
        report["checked_at"] = datetime.now().isoformat()
        report["reference_count"] = len(kps)
        return report

    def batch_check(self, projects):
        """批量检查多个项目"""
        results = []
        for p in projects:
            r = self.check_project(p.get("description",""), p.get("type","land_remediation"))
            results.append(r)
        return results

    def generate_government_report(self, county_name, project_types=None):
        """生成某县的完整合规报告(含所有相关项目类型的政策风险概览)"""
        if project_types is None:
            project_types = ["land_remediation", "increase_decrease_hook", "high_standard_farmland"]

        sections = []
        for pt in project_types:
            check = self.check_project(f"{county_name}全域土地综合整治项目", pt)
            sections.append(check)

        return {
            "county": county_name,
            "generated_at": datetime.now().isoformat(),
            "sections": sections,
            "summary": self._ai_summarize_report(sections, county_name),
        }

    def _fetch_relevant_policies(self, project_type, limit=30):
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("""SELECT id, title, original_excerpt, ai_extracted_content, qa_score
                         FROM knowledge_points WHERE review_status IN ('confirmed','pending')
                         AND content_type='policy'
                         ORDER BY qa_score DESC LIMIT ?""", (limit,))
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def _format_kps(self, kps):
        return "\n".join([f"- {kp['title'][:100]}: {(kp.get('original_excerpt') or '')[:200]}"
                         for kp in kps[:20]])

    def _ai_compliance_check(self, project_desc, kp_text, project_type):
        system_prompt = f"""你是乡村振兴政策合规审查专家。请检查以下项目方案是否符合四川省现行政策。

参考政策知识库:
{kp_text}

请逐项检查:
1. 用地合规性(耕地保护/永久基本农田/生态红线)
2. 指标合规性(增减挂钩/占补平衡指标是否在允许范围内)
3. 程序合规性(审批流程/公示要求/听证要求)
4. 资金合规性(专项债/政策性贷款使用是否合规)
5. 补偿合规性(拆迁补偿标准/安置方案是否符合政策)

对每个风险点给出:
- risk_level: high/medium/low
- policy_basis: 引用具体政策条款
- peer_precedent: 四川省内同类项目的处理方式
- mitigation: 建议的合规修正方案

最后给出 overall_compliance: compliant/conditional/non_compliant

返回JSON。"""

        user_prompt = f"项目类型: {project_type}\n项目描述: {project_desc[:2000]}"

        try:
            resp = self.client.chat_with_json(system_prompt, user_prompt,
                                              temperature=0.1, model_override="deepseek-v4-pro",
                                              call_type="compliance_check")
            return resp.get("parsed_json") if isinstance(resp, dict) else {"error": "AI检查失败"}
        except Exception:
            return {"error": "AI检查异常"}

    def _ai_summarize_report(self, sections, county_name):
        try:
            summary_text = json.dumps([s.get("overall_compliance","?") for s in sections], ensure_ascii=False)
            resp = self.client.chat_with_json(
                f"请为{county_name}的乡村振兴项目合规检查生成200字以内的总结和建议。各项目合规状态: {summary_text}",
                "请生成总结",
                temperature=0.1, model_override="deepseek-v4-flash",
                call_type="compliance_summary"
            )
            return resp.get("parsed_json") if isinstance(resp, dict) else {}
        except Exception:
            return {}
