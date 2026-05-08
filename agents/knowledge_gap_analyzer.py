"""
knowledge_gap_analyzer.py - 知识缺口分析器(课程体系→倒推需求→自动化管道)
路径：agents/knowledge_gap_analyzer.py
版本：v2.3.7

CEO的核心工具: 课程体系→知识需求→知识库现状对比→缺口清单→爬取任务→喂料计划。
实现从"被动等老唐喂料"到"CEO主动构建知识管道"的转变。
"""

from datetime import datetime

from agents.course_system import get_course_system, get_knowledge_needs


class KnowledgeGapAnalyzer(object):
    """知识缺口分析器。课程体系→倒推需求→对比现状→生成任务。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client
        self.course_system = get_course_system()
        self.knowledge_needs = get_knowledge_needs()

    # ================================================================
    # 主方法: 全量缺口分析
    # ================================================================
    def analyze_all_gaps(self):
        """全面分析: 课程体系的每一项知识需求,知识库覆盖了多少,缺了什么。"""
        needs = self.knowledge_needs["all_needs"]
        gaps = []
        covered = []
        partial = []

        for item in needs:
            knowledge = item["knowledge"]
            lesson_count = item["lesson_count"]

            # 查询知识库覆盖度
            coverage = self._check_coverage(knowledge)

            if coverage["kp_count"] >= 5:
                covered.append(
                    {
                        "knowledge": knowledge,
                        "kps": coverage["kp_count"],
                        "lesson_count": lesson_count,
                    }
                )
            elif coverage["kp_count"] >= 1:
                partial.append(
                    {
                        "knowledge": knowledge,
                        "kps": coverage["kp_count"],
                        "lesson_count": lesson_count,
                        "missing_aspects": coverage.get("missing", []),
                    }
                )
            else:
                gaps.append(
                    {
                        "knowledge": knowledge,
                        "lesson_count": lesson_count,
                        "priority": (
                            "P0"
                            if lesson_count >= 3
                            else "P1" if lesson_count >= 2 else "P2"
                        ),
                        "suggested_sources": self._suggest_sources(knowledge),
                    }
                )

        return {
            "analyzed_at": datetime.now().isoformat(),
            "total_knowledge_needs": len(needs),
            "covered": len(covered),
            "partial": len(partial),
            "gaps": len(gaps),
            "coverage_rate": round(100 * len(covered) / max(1, len(needs)), 1),
            "gaps_detail": gaps,
            "covered_detail": covered[:10],
            "partial_detail": partial[:10],
        }

    def _check_coverage(self, knowledge):
        """检查知识库对某项知识的覆盖度"""
        if not self.db:
            return {"kp_count": 0, "missing": []}
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            # 用知识需求中的关键词搜索
            keywords = (
                knowledge.replace("（", " ")
                .replace("）", " ")
                .replace("、", " ")
                .split()
            )
            keywords = [k for k in keywords if len(k) >= 3][:3]
            total = 0
            for kw in keywords:
                c.execute(
                    """SELECT COUNT(*) FROM knowledge_points
                             WHERE (title LIKE ? OR original_excerpt LIKE ?)
                             AND review_status='confirmed'""",
                    (f"%{kw}%", f"%{kw}%"),
                )
                total += c.fetchone()[0]
            conn.close()
            return {"kp_count": min(total, 99), "missing": []}
        except Exception:
            return {"kp_count": 0, "missing": []}

    def _suggest_sources(self, knowledge):
        """根据知识需求建议爬取来源"""
        source_map = {
            "政策": ["自然资源部官网", "四川省自然资源厅", "四川省农业农村厅"],
            "案例": ["四川日报/川观新闻", "各市公共资源交易中心", "农发行项目公告"],
            "标准": ["住建部标准定额司", "自然资源部标准库", "国家标准全文公开系统"],
            "贷款": ["农发行官网", "国开行官网", "中国PPP中心"],
            "专项债": ["财政部官网", "中国地方政府债券信息公开平台"],
            "申报": ["国家发改委", "四川省发改委", "各市农业农村局"],
            "方案": ["政府采购网(方案招标公告)", "各市公共资源交易平台"],
            "合作社": ["农业农村部乡村产业发展司", "四川省农业农村厅产业处"],
            "验收": ["住建部标准定额司", "四川省建设工程质量安全监督总站"],
        }

        suggested = []
        for keyword, sources in source_map.items():
            if keyword in knowledge:
                suggested.extend(sources)
        if not suggested:
            suggested = ["四川省自然资源厅", "四川省农业农村厅", "相关市州政府网站"]
        return suggested[:5]

    # ================================================================
    # 生成CEO行动指令
    # ================================================================
    def generate_ceo_instructions(self):
        """生成给CEO的行动指令: 优先爬取什么,喂什么料。"""
        analysis = self.analyze_all_gaps()
        gaps = analysis["gaps_detail"]

        # P0: 被3个以上课程引用且知识库为空
        p0_gaps = [g for g in gaps if g["priority"] == "P0"]

        instructions = {
            "summary": f"覆盖率{analysis['coverage_rate']}%, {analysis['gaps']}个缺口需补齐",
            "immediate_actions": [],
            "weekly_plan": [],
        }

        if p0_gaps:
            instructions["immediate_actions"].append(
                {
                    "action": "P0紧急喂料",
                    "targets": [
                        {"knowledge": g["knowledge"], "sources": g["suggested_sources"]}
                        for g in p0_gaps[:5]
                    ],
                    "deadline": "48小时内完成首批爬取和提取",
                    "responsible_agent": "feed_strategist",
                }
            )

        # P1: 被2个课程引用且知识库不足
        p1_gaps = [g for g in gaps if g["priority"] == "P1"]
        if p1_gaps:
            instructions["weekly_plan"].append(
                {
                    "week": 1,
                    "targets": [{"knowledge": g["knowledge"]} for g in p1_gaps[:8]],
                    "responsible_agent": "feed_strategist",
                }
            )

        return instructions

    def to_dict(self):
        return {
            "agent_code": "knowledge_gap_analyzer",
            "agent_name": "知识缺口分析器",
            "agent_type": "analysis",
            "identity_text": "我是知识缺口分析器。我从课程体系倒推知识需求,对比知识库现状,找到缺口,生成爬取和喂料任务。我是CEO'主动构建知识管道'的核心工具。",
        }
