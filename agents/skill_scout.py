"""
skill_scout.py - 技能侦察员: 在GitHub上寻找有价值开源skill,评估商业价值+安全性,推荐整合
路径：agents/skill_scout.py
版本：v2.3.7
"""
import json, time, sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.base_agent import BaseAgent


class SkillScout(BaseAgent):
    """技能侦察员 — 在GitHub寻找有价值开源项目,从商业价值和安全性两个维度评估,推荐整合方案。"""

    def __init__(self, agent_code, agent_name, specialization, client=None, db=None):
        identity_map = {
            "nlp": (
                "我是NLP技能侦察员。我专精中文自然语言处理领域的开源工具评估。"
                "我看: 分词/实体识别/文本向量化/语义搜索/情感分析。"
                "我的收入贡献: 更强的NLP=更好的知识提取=更多可卖钱的知识点。"
            ),
            "gov_data": (
                "我是政府数据侦察员。我搜索政策文档解析、PDF提取、法规NLP、政务数据采集工具。"
                "我看: OCR/文档结构解析/表格提取/政策文本分类/法规知识图谱。"
                "我的收入贡献: 更快更准的政策解析=独家内容优势=客户付费理由。"
            ),
            "security": (
                "我是安全侦察员。我扫描内容安全、敏感词检测、代码安全审计、数据隐私保护工具。"
                "我看: 敏感词过滤/垃圾检测/隐私合规/安全扫描/防注入。"
                "我的收入贡献: 安全合规=品牌保护=客户信任=续费率。"
            ),
        }
        identity = identity_map.get(specialization, identity_map["nlp"])
        self.specialization = specialization
        self._scout_log = []

        super().__init__(
            agent_code=agent_code, agent_name=agent_name, agent_type="scout",
            identity_text=identity,
            core_questions=[
                "这个开源项目解决什么问题?和我们的知识工厂有什么关联?",
                "许可证是否允许商业使用?有没有法律风险?",
                "整合成本多高?是直接可用还是要大量改造?",
                "这个工具能直接提升我们的产品竞争力吗?能帮我们多赚钱吗?",
                "有没有安全风险?依赖链是否健康?维护者是否活跃?",
            ],
            quality_standards=[
                "只推荐许可证允许商业使用的项目(Apache/MIT/BSD)",
                "必须评估整合成本和预期收益(ROI)",
                "安全性必须通过: 无恶意代码/无敏感数据泄露/依赖链健康",
                "每个推荐必须有具体的整合方案,不是'这个不错可以用'",
                "优先级排序: 能直接提升收入 > 提升效率 > 锦上添花",
            ],
            scoring_dimensions=[
                "商业价值匹配度", "整合成本可行度", "安全合规度",
                "社区活跃度", "与现有技术栈兼容度"
            ],
            client=client, db=db,
        )

    def search_github(self, keywords, max_results=10):
        """通过AI搜索GitHub相关开源项目。
        因为SkillScout是AI Agent,用think()能力在知识范围内检索和评估开源项目。
        返回: [{name, url, stars, description, license, last_updated, ...}]
        """
        search_prompt = f"""你是一个开源技术侦察专家。请搜索GitHub上与以下关键词相关的开源项目:
关键词: {keywords}

请找出最相关的{max_results}个开源项目(优先高star、活跃维护的项目)。

返回JSON数组:
[{{
  "name": "项目名",
  "url": "https://github.com/owner/repo",
  "stars": "约Xk stars",
  "description": "一句话描述(中文)",
  "license": "MIT/Apache/GPL/...",
  "last_updated": "最近更新日期",
  "language": "主要语言",
  "relevance_reason": "为什么和我们相关"
}}]

只返回真实存在的项目,不确定的项目不要列。"""

        try:
            result = self.think({"task": "github_search", "query": search_prompt}, deep=True)
            self._scout_log.append({
                "action": "search", "keywords": keywords,
                "time": datetime.now().isoformat(),
            })
            return {
                "keywords": keywords,
                "analysis": result.get("analysis", ""),
                "insights": result.get("insights", []),
                "recommendations": result.get("recommendations", []),
            }
        except Exception as e:
            self._scout_log.append({
                "action": "search_error", "keywords": keywords,
                "error": str(e)[:200],
            })
            return {"keywords": keywords, "error": str(e)[:200]}

    def evaluate_skill(self, repo_info):
        """评估一个开源skill的商业价值和安全性。
        repo_info: dict with {name, url, description, license, ...}
        返回: {commercial_value, moat_contribution, safety_risk, integration_effort, recommendation}
        """
        eval_prompt = f"""评估以下开源项目对我们乡村振兴知识工厂的价值:

项目: {repo_info.get('name','?')}
网址: {repo_info.get('url','?')}
描述: {repo_info.get('description','?')}
许可证: {repo_info.get('license','?')}
Stars: {repo_info.get('stars','?')}

评估维度(每个1-5分):
1. 商业价值: 这个工具能直接帮我们赚钱(提升产品质量/降低生产成本/开拓新收入)?
2. 护城河贡献: 这个工具能帮我们建立竞争壁垒(独家能力/差异化/用户粘性)?
3. 安全风险: low(完全安全)/medium(需审查)/high(有明显风险)
4. 整合难度: easy(~1天)/medium(~3天)/hard(1周+)
5. 与现有技术栈兼容度: Python生态优先 / 需要桥接 / 完全异构

返回JSON:
{{
  "commercial_value": 1-5(附≤30字理由),
  "moat_contribution": 1-5(附≤30字理由),
  "safety_risk": "low/medium/high",
  "integration_effort": "easy/medium/hard",
  "tech_compatibility": "native/bridge/alien",
  "overall_score": 1-10,
  "recommendation": "adopt/evaluate/reject",
  "rationale": "≤100字综合评估"
}}"""

        try:
            result = self.think({"task": "evaluate_skill", "repo": repo_info}, deep=True)
            return {
                "repo": repo_info.get("name", "?"),
                "url": repo_info.get("url", ""),
                "commercial_value": result.get("analysis", ""),
                "insights": result.get("insights", []),
                "recommendations": result.get("recommendations", []),
                "confidence": result.get("confidence", "medium"),
            }
        except Exception as e:
            return {
                "repo": repo_info.get("name", "?"),
                "error": str(e)[:200],
            }

    def generate_integration_plan(self, approved_skills):
        """为批准的skill生成整合方案。
        approved_skills: [{repo_info, evaluation, ...}]
        返回: {summary, steps, estimated_cost, estimated_benefit, risks}
        """
        plan_prompt = f"""为以下{len(approved_skills)}个通过评估的开源项目生成整合方案:

{json.dumps(approved_skills, ensure_ascii=False)[:2000]}

返回JSON整合方案:
{{
  "summary": "≤100字方案概述",
  "steps": [
    {{"step": 1, "action": "具体行动", "owner": "负责Agent", "effort": "estimated hours"}}
  ],
  "estimated_cost": "预计API/人力成本",
  "estimated_benefit": "≤100字预期商业收益",
  "risks": ["风险1", "风险2"],
  "priority_order": ["项目1优先", "项目2次之"],
  "timeline": "预计完成时间"
}}"""

        try:
            result = self.think({"task": "integration_plan", "skills": approved_skills}, deep=True)
            return {
                "plan": result.get("analysis", ""),
                "insights": result.get("insights", []),
                "recommendations": result.get("recommendations", []),
            }
        except Exception as e:
            return {"error": str(e)[:200]}

    def scout_mission(self):
        """执行一次完整的侦察任务: 搜索→评估→推荐。"""
        domains = {
            "nlp": ["chinese text embedding open source", "chinese semantic search github", "chinese NLP toolkit 2025"],
            "gov_data": ["chinese government document parser github", "pdf table extractor chinese open source", "policy text analyzer python"],
            "security": ["chinese sensitive word detection github", "content safety filter open source", "text moderation api python"],
        }
        keywords_list = domains.get(self.specialization, domains["nlp"])

        all_results = []
        for kw in keywords_list[:2]:
            result = self.search_github(kw)
            all_results.append(result)

        summary = {
            "scout": self.agent_name,
            "specialization": self.specialization,
            "mission_time": datetime.now().isoformat(),
            "searches": len(all_results),
            "findings": all_results,
        }
        self._scout_log.append({
            "action": "mission", "specialization": self.specialization,
            "searches": len(all_results), "time": datetime.now().isoformat(),
        })
        return summary

    def get_scout_stats(self):
        return {
            "agent_code": self.agent_code,
            "agent_name": self.agent_name,
            "specialization": self.specialization,
            "missions": len(self._scout_log),
            "total_calls": self._call_count,
            "total_cost": round(self._total_cost, 4),
        }


def build_skill_scouts(client=None, db=None):
    """构建3个SkillScout侦察员,返回列表。"""
    scouts = []

    scouts.append(SkillScout(
        "chinese_nlp_scout", "NLP技能侦察员", "nlp",
        client=client, db=db,
    ))

    scouts.append(SkillScout(
        "gov_data_scout", "政府数据侦察员", "gov_data",
        client=client, db=db,
    ))

    scouts.append(SkillScout(
        "security_scout", "安全侦察员", "security",
        client=client, db=db,
    ))

    return scouts
