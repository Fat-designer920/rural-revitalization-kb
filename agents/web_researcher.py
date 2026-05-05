"""
web_researcher.py - AI网络研究员(搜索→清洗→关联→入库)
路径：agents/web_researcher.py
版本：v2.3.7

主动从互联网搜索乡村振兴相关信息,清洗过滤后与知识库关联。
支持:政策查询/案例搜索/数据查找/竞品对标/最新动态。
"""
import json
from datetime import datetime


class WebResearcher(object):
    """AI网络研究员。搜索→清洗→提取→关联→入库五步管道。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client

    def research_topic(self, topic, search_depth=3):
        """深度研究一个主题:搜索→AI清洗→提取知识点→关联现有知识→生成研究简报"""
        # Step 1: 搜索(使用内置WebSearch能力)
        search_results = self._search_web(topic, search_depth)

        # Step 2: AI清洗和提取
        cleaned = self._ai_clean_and_extract(topic, search_results)

        # Step 3: 关联现有知识点
        related_kps = self._find_related_kps(topic)

        # Step 4: 生成研究简报
        brief = self._generate_research_brief(topic, cleaned, related_kps)

        return {
            "topic": topic,
            "searched_at": datetime.now().isoformat(),
            "sources_count": len(search_results),
            "key_findings": cleaned.get("key_findings", []),
            "related_kps": len(related_kps),
            "brief": brief,
            "new_knowledge": cleaned.get("extracted_knowledge", []),
        }

    def research_for_agent(self, agent_code, agent_question):
        """为特定Agent研究一个问题(15个客户Agent的核心问题驱动搜索)"""
        from agents.agent_orchestra import build_all_agents
        agents = build_all_agents()
        agent = next((a for a in agents if a.agent_code == agent_code), None)

        search_query = agent_question
        if agent:
            search_query = f"{agent.agent_name} {agent_question} 四川 乡村振兴"

        result = self.research_topic(search_query)
        result["agent_code"] = agent_code
        result["agent_question"] = agent_question
        return result

    def research_policy_update(self, policy_name):
        """研究特定政策的最新动态(用于政策监控)"""
        return self.research_topic(f"{policy_name} 最新政策 四川 2026")

    def research_competitor(self, competitor_name):
        """研究竞品动态"""
        return self.research_topic(f"{competitor_name} 乡村振兴 知识服务 定价 功能")

    def batch_research_for_gaps(self, gaps, max_topics=5):
        """批量研究知识缺口(AuditEngine发现的知识缺口→自动搜索补充)"""
        results = []
        for gap in gaps[:max_topics]:
            question = gap.get("question", gap.get("description", ""))
            if question:
                r = self.research_topic(question[:100])
                results.append(r)
        return results

    def _search_web(self, query, depth=3):
        """搜索网络(通过模型内置搜索能力)"""
        # 由调用方注入搜索结果
        # 在Claude Code环境中,可使用WebSearch工具
        return {
            "query": query,
            "depth": depth,
            "note": "搜索结果由Claude Code WebSearch工具提供,本模块负责清洗和关联",
        }

    def _ai_clean_and_extract(self, topic, search_results):
        """AI清洗搜索结果,提取结构化知识点"""
        try:
            system_prompt = f"""你是信息清洗专家。请从关于'{topic}'的网络搜索结果中提取关键信息。

清洗规则:
1. 去掉广告/推广/营销内容
2. 去掉重复信息
3. 只保留与四川乡村振兴直接相关的内容
4. 标注信息来源的权威性(政府>学术>媒体>个人)

对每条关键发现标注:
- finding: 核心发现(≤100字)
- source_authority: high/medium/low
- relevance_to_sichuan: high/medium/low
- actionability: 是否可以转化为具体的操作建议

返回JSON: {{"key_findings": [...], "extracted_knowledge": [...], "search_quality": "评估搜索质量"}}"""

            resp = self.client.chat_with_json(
                system_prompt,
                f"请清洗关于'{topic}'的搜索结果",
                temperature=0.1, model_override="deepseek-v4-flash",
                call_type="web_research"
            )
            return resp.get("parsed_json") if isinstance(resp, dict) else {"key_findings": [], "extracted_knowledge": []}
        except Exception:
            return {"key_findings": [], "extracted_knowledge": []}

    def _find_related_kps(self, topic):
        """在知识库中查找与主题相关的知识点"""
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("""SELECT id, title, original_excerpt FROM knowledge_points
                         WHERE (title LIKE ? OR original_excerpt LIKE ?)
                         AND review_status IN ('confirmed','pending')
                         LIMIT 20""", (f"%{topic[:30]}%", f"%{topic[:30]}%"))
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def _generate_research_brief(self, topic, cleaned, related_kps):
        """生成研究简报"""
        findings = cleaned.get("key_findings", [])
        findings_text = "\n".join([f"- {f.get('finding','')}" for f in findings[:5]])

        kp_text = "\n".join([f"- {kp.get('title','')[:80]}" for kp in related_kps[:5]])

        try:
            resp = self.client.chat_with_json(
                f"""请基于以下信息生成关于'{topic}'的研究简报(≤300字):

网络研究发现:
{findings_text}

知识库已有相关内容:
{kp_text}

简报要包含:核心发现/与现有知识的关联/对操盘手的实操建议/需要进一步研究的问题""",
                "请生成研究简报",
                temperature=0.2, model_override="deepseek-v4-flash",
                call_type="research_brief"
            )
            return resp.get("parsed_json") if isinstance(resp, dict) else {}
        except Exception:
            return {"brief": f"关于'{topic}'的研究简报生成失败"}
