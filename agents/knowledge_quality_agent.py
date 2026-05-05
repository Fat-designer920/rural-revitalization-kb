"""
knowledge_quality_agent.py - 知识质量Agent(CEO指令:自动化QA校验,提质量降人工)
路径：agents/knowledge_quality_agent.py
版本：v2.3.7

CEO战略决策:质量已成为瓶颈。本Agent负责逐条校验知识点的一致性和专业度。
使命:让每一条入库的知识都达到"可以直接给客户看"的标准。
"""
import json
from datetime import datetime


class KnowledgeQualityAgent(object):
    """知识质量Agent。5维度自动校验,不通过=不入库。"""

    QUALITY_DIMENSIONS = {
        "factual_accuracy": "事实准确性(政策条款/数据/文件号是否正确)",
        "relevance": "相关性(是否与四川乡村振兴直接相关,拒绝泛泛而谈)",
        "actionability": "可操作性(是否有具体的操作步骤/案例/模板,拒绝空泛原则)",
        "clarity": "表达清晰度(是否通俗易懂,村支书能看懂,拒绝官话套话)",
        "completeness": "信息完整度(是否有标题/摘要/出处/时效信息)",
    }

    REJECT_RULES = [
        "纯口号/表态语言(如'要高度重视乡村振兴')",
        "信息过时超过3年的政策条款(除非标注历史参考)",
        "与已有知识点重复度>80%(标记为重复,不重复入库)",
        "来源不可靠(个人微博/朋友圈/未经验证的帖子)",
        "内容过于简短(原文摘录<50字且无实质信息)",
        "与四川无关(全国性政策但无四川落地指引=需补充四川视角)",
    ]

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client

    def audit_batch(self, kp_ids, sample_size=50):
        """批量质量审计。返回通过/不通过/需修改三组。"""
        kps = self._fetch_kps(kp_ids, sample_size)
        if not kps:
            return {"passed": 0, "failed": 0, "needs_fix": 0, "total": 0}

        results = {"passed": [], "failed": [], "needs_fix": [], "total": len(kps)}

        for kp in kps:
            verdict = self._judge_single(kp)
            results[verdict["verdict"]].append({
                "kp_id": kp.get("id"),
                "title": kp.get("title", "")[:80],
                "verdict": verdict["verdict"],
                "reason": verdict.get("reason", ""),
                "score": verdict.get("score", 0),
            })

        # 自动标记 fail 的知识点
        if results["failed"]:
            self._auto_flag_failed(results["failed"])

        return {
            "passed": len(results["passed"]),
            "failed": len(results["failed"]),
            "needs_fix": len(results["needs_fix"]),
            "total": len(kps),
            "pass_rate": len(results["passed"]) / max(1, len(kps)),
            "details": results,
        }

    def _judge_single(self, kp):
        """AI判断单条知识点质量。返回verdict + reason + score。"""
        title = kp.get("title", "")[:100]
        excerpt = (kp.get("original_excerpt") or "")[:300]
        ctype = kp.get("content_type", "policy")
        tags = kp.get("suggested_category_tags") or "[]"

        system_prompt = f"""你是知识质量审查员。请审查这条乡村振兴知识点。

标题: {title}
类型: {ctype}
摘录: {excerpt}
标签: {tags}

审查标准:
1. 事实准确? (政策条款/数据/文件号正确吗)
2. 与四川乡村振兴相关? (无关=直接拒绝)
3. 有可操作性? (具体的步骤/方法/案例,不是空泛原则)
4. 表达清晰? (通俗易懂,村支书能看懂)
5. 信息完整? (有出处/时效信息)

拒绝规则:
{chr(10).join('- '+r for r in self.REJECT_RULES)}

返回JSON:
{{
  "verdict": "passed/failed/needs_fix",
  "score": 1-5,
  "reason": "≤80字理由",
  "suggested_fix": "如果是needs_fix,给出具体修改建议≤100字"
}}"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, f"请审查: {title}",
                temperature=0.1, model_override="deepseek-v4-flash",
                call_type="quality_audit"
            )
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            return {
                "verdict": parsed.get("verdict", "needs_fix"),
                "score": parsed.get("score", 3),
                "reason": parsed.get("reason", ""),
                "suggested_fix": parsed.get("suggested_fix", ""),
            }
        except Exception:
            return {"verdict": "needs_fix", "score": 3, "reason": "AI审查异常,默认需人工复查"}

    def generate_quality_report(self):
        """生成全库质量报告→提交CEO"""
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM knowledge_points")
            total = c.fetchone()[0]
            c.execute("SELECT AVG(qa_score) FROM knowledge_points")
            avg_qa = c.fetchone()[0] or 0
            c.execute("SELECT content_type, COUNT(*) FROM knowledge_points GROUP BY content_type")
            type_dist = {r[0]: r[1] for r in c.fetchall()}
            c.execute("SELECT COUNT(*) FROM knowledge_points WHERE LENGTH(original_excerpt) < 100")
            short_kps = c.fetchone()[0]
            conn.close()

            return {
                "total_kps": total,
                "avg_qa_score": round(avg_qa, 1),
                "short_kps_pct": round(100 * short_kps / max(1, total), 1),
                "type_distribution": type_dist,
                "quality_assessment": self._assess_overall_quality(total, avg_qa, short_kps),
                "generated_at": datetime.now().isoformat(),
            }
        except Exception:
            return {"error": "报告生成失败"}

    def _fetch_kps(self, kp_ids, limit):
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            if kp_ids:
                placeholders = ",".join("?" * len(kp_ids[:limit]))
                c.execute(f"SELECT * FROM knowledge_points WHERE id IN ({placeholders}) LIMIT ?",
                          kp_ids[:limit] + [limit])
            else:
                c.execute("SELECT * FROM knowledge_points ORDER BY RANDOM() LIMIT ?", (limit,))
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def _auto_flag_failed(self, failed_kps):
        """自动标记不通过的知识点(降低就绪度)"""
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            for kp in failed_kps[:20]:
                c.execute("UPDATE knowledge_points SET content_readiness='draft' WHERE id=?",
                          (kp["kp_id"],))
            conn.commit(); conn.close()
        except Exception:
            pass

    def _assess_overall_quality(self, total, avg_qa, short_kps):
        if avg_qa >= 4.0:
            return "知识库整体质量较高,可以开始市场验证"
        elif avg_qa >= 3.0:
            return "知识库质量中等,建议加强深度解读和四川本地案例"
        else:
            return "知识库质量偏低,建议暂停大规模喂料,优先提升已有内容质量"
