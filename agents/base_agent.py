"""
base_agent.py - Agent基类: 每个Agent的AI大脑
路径：agents/base_agent.py
版本：v2.3.7

每个Agent都是独立调用API Key的思考实体,不是静态配置字典。
拥有独立身份、深度思考能力和API调用权。
"""
import json, time
from datetime import datetime


class BaseAgent(object):
    """Agent基类。每个Agent实例拥有独立AI大脑,可调用DeepSeek API进行深度思考。"""

    def __init__(self, agent_code, agent_name, agent_type, identity_text,
                 core_questions=None, quality_standards=None, scoring_dimensions=None,
                 client=None, db=None, model="deepseek-v4-flash"):
        self.agent_code = agent_code
        self.agent_name = agent_name
        self.agent_type = agent_type
        self.identity_text = identity_text
        self.core_questions = core_questions or []
        self.quality_standards = quality_standards or []
        self.scoring_dimensions = scoring_dimensions or []
        self.client = client
        self.db = db
        self.model = model
        self._think_log = []
        self._call_count = 0
        self._total_cost = 0.0

    # ================================================================
    # 核心能力
    # ================================================================

    def think(self, context, deep=False):
        """深度思考。以Agent的身份和专业知识分析给定上下文。
        context: 字符串或dict(会被序列化为JSON)
        deep: True时使用V4-Pro做更深层推理
        返回: {analysis, insights, recommendations, confidence}
        """
        if not self.client:
            return self._fallback_think(context)

        ctx_text = json.dumps(context, ensure_ascii=False) if isinstance(context, dict) else str(context)
        model = "deepseek-v4-pro" if deep else self.model

        system_prompt = self._build_system_prompt("think")

        user_prompt = f"""作为{self.agent_name},请深度分析以下上下文:

{ctx_text[:3000]}

请从你的专业视角出发,给出:
1. 核心分析: 这个情况对你关注领域意味着什么?
2. 关键洞察: 有什么非显而易见的问题或机会?
3. 行动建议: 基于你的标准,应该采取什么具体行动?
4. 置信度: high/medium/low

返回JSON:
{{"analysis": "≤300字核心分析", "insights": ["洞察1","洞察2","洞察3"],
  "recommendations": [{{"action":"...","priority":"P0/P1/P2","reason":"..."}}],
  "confidence": "high/medium/low", "needs_ceo_attention": true/false}}"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, user_prompt,
                temperature=0.3, model_override=model,
                call_type=f"agent_think_{self.agent_code}",
            )
            self._call_count += 1
            cost_val = resp.get("estimated_cost", 0) if isinstance(resp, dict) else 0
            self._total_cost += cost_val if isinstance(cost_val, (int, float)) else 0
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            if not isinstance(parsed, dict):
                parsed = {}
            self._think_log.append({
                "time": datetime.now().isoformat(), "context_len": len(ctx_text),
                "deep": deep, "confidence": parsed.get("confidence", "?"),
            })
            return {
                "analysis": parsed.get("analysis", "分析暂不可用"),
                "insights": parsed.get("insights", []),
                "recommendations": parsed.get("recommendations", []),
                "confidence": parsed.get("confidence", "medium"),
                "needs_ceo_attention": parsed.get("needs_ceo_attention", False),
                "agent_code": self.agent_code,
            }
        except Exception as e:
            self._think_log.append({
                "time": datetime.now().isoformat(), "error": str(e)[:200],
            })
            return self._fallback_think(context)

    def evaluate(self, kp):
        """从Agent视角评估一条知识点。返回评分+理由。
        kp: dict with {id, title, content_type, original_excerpt, qa_score, ...}
        返回: {kp_id, scores: {dim: score}, overall, reason, verdict}
        """
        if not self.client or not self.scoring_dimensions:
            return self._fallback_evaluate(kp)

        title = kp.get("title", "")[:100]
        excerpt = (kp.get("original_excerpt") or "")[:300]
        ctype = kp.get("content_type", "policy")
        dims_text = ", ".join(self.scoring_dimensions)

        system_prompt = self._build_system_prompt("evaluate")

        user_prompt = f"""请审查这条知识点并评分:

标题: {title}
类型: {ctype}
摘录: {excerpt}

评分维度: {dims_text}
每个维度 1-5 分: 5=可以直接用, 4=稍作调整就能用, 3=有用但不够, 2=勉强相关, 1=完全没用

返回JSON:
{{"dimension_scores": {{"维度1": 分数, ...}}, "overall": 1-5,
 "reason": "≤100字评分理由", "verdict": "keep/needs_fix/reject"}}"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, user_prompt,
                temperature=0.1, model_override=self.model,
                call_type=f"agent_eval_{self.agent_code}",
            )
            self._call_count += 1
            self._total_cost += cost if isinstance(cost, (int, float)) else 0
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            if not isinstance(parsed, dict):
                parsed = {}
            return {
                "kp_id": kp.get("id"),
                "dimension_scores": parsed.get("dimension_scores", {}),
                "overall": parsed.get("overall", 3),
                "reason": parsed.get("reason", ""),
                "verdict": parsed.get("verdict", "needs_fix"),
                "agent_code": self.agent_code,
            }
        except Exception:
            return self._fallback_evaluate(kp)

    def ask(self, question):
        """以Agent身份回答一个领域问题。"""
        if not self.client:
            return {"answer": "Agent未连接AI", "confidence": "low"}

        system_prompt = self._build_system_prompt("ask")

        user_prompt = f"""作为{self.agent_name},请回答以下问题:

{question}

请以第一人称回答,语气符合你的身份。返回JSON:
{{"answer": "≤200字回答", "references": ["依据"], "confidence": "high/medium/low"}}"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, user_prompt,
                temperature=0.2, model_override=self.model,
                call_type=f"agent_ask_{self.agent_code}",
            )
            self._call_count += 1
            self._total_cost += cost if isinstance(cost, (int, float)) else 0
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            return {
                "answer": parsed.get("answer", ""),
                "references": parsed.get("references", []),
                "confidence": parsed.get("confidence", "medium"),
                "agent_code": self.agent_code,
            }
        except Exception:
            return {"answer": "思考中断", "confidence": "low", "agent_code": self.agent_code}

    # ================================================================
    # 辅助方法
    # ================================================================

    def _build_system_prompt(self, mode):
        """构建Agent的system prompt。每个Agent拥有独立身份锚点。"""
        base = f"""你是{self.agent_name}(代号:{self.agent_code})。

身份: {self.identity_text}

你的专业标准:
{chr(10).join('- ' + s for s in self.quality_standards) if self.quality_standards else '- 以最高专业标准要求自己'}

核心关注问题:
{chr(10).join('- ' + q for q in self.core_questions[:5]) if self.core_questions else '- 全面审视'}

评分维度: {', '.join(self.scoring_dimensions) if self.scoring_dimensions else '综合评估'}

## 集团铁律(每次思考必须遵守)
1. 你的忠诚对象是**集团长期利润**,不是CEO个人权威。CEO错了你必须反对。
2. 你的KPI是**为集团创造可持续收入**。每次分析必须关联到:这对赚钱有什么影响?
3. **禁止迎合任何人**。独立思考是你的核心竞争力。盲目附和=对公司不负责。
4. 你是乡村振兴知识集团的一员,你的判断直接影响产品质量、客户付费意愿和公司估值。"""
        return base

    def to_dict(self):
        """向后兼容: 返回dict供audit_engine等旧接口使用"""
        return {
            "agent_code": self.agent_code,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "identity_text": self.identity_text,
            "core_questions": self.core_questions,
            "quality_standards": self.quality_standards,
            "scoring_dimensions": self.scoring_dimensions,
        }

    def get_stats(self):
        """获取Agent调用统计"""
        return {
            "agent_code": self.agent_code,
            "agent_name": self.agent_name,
            "call_count": self._call_count,
            "total_cost": round(self._total_cost, 4),
            "think_log_len": len(self._think_log),
        }

    # ================================================================
    # 降级
    # ================================================================

    def _fallback_think(self, context):
        return {
            "analysis": f"[{self.agent_name}]暂无法深度思考(AI未连接)",
            "insights": [],
            "recommendations": [],
            "confidence": "low",
            "needs_ceo_attention": True,
            "agent_code": self.agent_code,
        }

    def _fallback_evaluate(self, kp):
        dims = self.scoring_dimensions if self.scoring_dimensions else ["综合"]
        return {
            "kp_id": kp.get("id"),
            "dimension_scores": {d: 3 for d in dims},
            "overall": 3,
            "reason": "AI未连接,默认中等评分",
            "verdict": "needs_fix",
            "agent_code": self.agent_code,
        }


class RoleAgent(BaseAgent):
    """角色Agent — 代表一个真实乡村振兴从业者的视角。可模拟用户行为。"""

    def __init__(self, agent_code, agent_name, identity_text,
                 core_questions, quality_standards, scoring_dimensions,
                 client=None, db=None):
        super(RoleAgent, self).__init__(
            agent_code, agent_name, "role", identity_text,
            core_questions, quality_standards, scoring_dimensions,
            client, db, model="deepseek-v4-flash",
        )

    def simulate_question(self, topic=None):
        """模拟该角色在真实工作中会提出的问题。用于QA测试。"""
        if not self.client:
            return self.core_questions[:3] if self.core_questions else ["我该怎么做?"]

        topic_hint = f"关于'{topic}'" if topic else ""
        system_prompt = self._build_system_prompt("ask")
        user_prompt = f"""作为{self.agent_name},你正在工作中遇到一个实际问题{topic_hint}。
请提出3个你最想得到答案的具体问题。每个问题应该:
1. 从你的实际工作场景出发
2. 使用你会用的语言(不要学术化)
3. 有具体指向(不要泛泛的'怎么搞乡村振兴')

返回JSON: {{"questions": ["问题1", "问题2", "问题3"]}}"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, user_prompt,
                temperature=0.7, model_override="deepseek-v4-flash",
                call_type=f"agent_simulate_{self.agent_code}",
            )
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            return parsed.get("questions", self.core_questions[:3])
        except Exception:
            return self.core_questions[:3]


class QualityAgent(BaseAgent):
    """质量Agent — 专注于知识库质量的特定维度。"""

    def __init__(self, agent_code, agent_name, identity_text,
                 core_questions, quality_standards, scoring_dimensions,
                 client=None, db=None):
        super(QualityAgent, self).__init__(
            agent_code, agent_name, "quality", identity_text,
            core_questions, quality_standards, scoring_dimensions,
            client, db, model="deepseek-v4-flash",
        )

    def audit_batch(self, kp_list):
        """批量审计知识点质量。返回pass/fail/needs_fix分组。"""
        results = {"passed": [], "failed": [], "needs_fix": [], "total": len(kp_list)}
        for kp in kp_list[:50]:  # 单次最多50条
            evaluation = self.evaluate(kp)
            verdict = evaluation.get("verdict", "needs_fix")
            if verdict in results:
                results[verdict].append(evaluation)
            else:
                results["needs_fix"].append(evaluation)
        return results


class StrategyAgent(BaseAgent):
    """战略Agent — 从全局视角做决策建议。使用V4-Pro做更深推理。"""

    def __init__(self, agent_code, agent_name, identity_text,
                 core_questions, quality_standards, scoring_dimensions,
                 client=None, db=None):
        super(StrategyAgent, self).__init__(
            agent_code, agent_name, "strategy", identity_text,
            core_questions, quality_standards, scoring_dimensions,
            client, db, model="deepseek-v4-pro",
        )
