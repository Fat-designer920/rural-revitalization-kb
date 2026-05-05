"""
meeting_engine.py - 集团公司会议决策引擎(独立观点→辩论→共识→CEO裁决)
路径：agents/meeting_engine.py
版本：v2.3.7

集团公司不是一人独裁。重大决策必须经过:
  1. CEO提议题 → 2. 召集相关部门Agent → 3. 首轮独立表态(禁止迎合)
  → 4. 第二轮强制异议(每个Agent必须提不同意见) → 5. AI主持人综合
  → 6. CEO审阅辩论记录后裁决 → 7. 执行+下次复盘

核心铁律:
  - Agent的忠诚对象是集团利润,不是CEO
  - 禁止盲目附和,必须独立思考
  - 每个Agent以"为集团挣钱"为KPI锚点
"""
import json, time
from datetime import datetime


class MeetingEngine(object):
    """集团公司会议决策引擎。主持Agent辩论,产生共识报告,供CEO最终裁决。"""

    def __init__(self, client=None, db=None):
        self.client = client
        self.db = db
        self.meeting_log = []

    # ================================================================
    # 七步会议协议
    # ================================================================
    def convene(self, topic, agents, ceo_context=None):
        """召开一次完整会议。
        topic: 会议议题(字符串)
        agents: 参会Agent列表(BaseAgent实例,必须有client)
        ceo_context: CEO提供的背景信息
        返回: {minutes, consensus,分歧, recommendations, debate_transcript}
        """
        if len(agents) < 2:
            return self._single_analysis(topic, agents, ceo_context)

        meeting_id = f"M{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        transcript = []
        cost_total = 0.0

        # === Phase 1: 首轮独立表态 ===
        round1 = self._round1_independent_opinions(topic, agents, ceo_context)
        transcript.append({"phase": "首轮独立表态", "opinions": round1})
        cost_total += sum(o.get("cost", 0) for o in round1)

        # === Phase 2: 强制异议轮 ===
        round2 = self._round2_mandatory_dissent(topic, agents, round1)
        transcript.append({"phase": "强制异议轮", "dissents": round2})
        cost_total += sum(d.get("cost", 0) for d in round2)

        # === Phase 3: AI主持人综合 ===
        synthesis = self._round3_moderator_synthesis(topic, round1, round2)
        transcript.append({"phase": "主持人综合", "synthesis": synthesis})
        cost_total += synthesis.get("cost", 0)

        # === Phase 3.5: 质量闸 ===
        low_quality = [e for e in synthesis.get("agent_evaluations", [])
                       if e.get("quality") == "low"]
        low_count = len(low_quality)
        if low_count >= max(1, len(agents) // 3):
            low_names = [e.get("agent", "?") for e in low_quality]
            return {
                "meeting_id": meeting_id,
                "quality_gate_blocked": True,
                "blocked_reason": f"质量闸触发: {low_count}/{len(agents)}个Agent论证质量低({', '.join(low_names)})。需要升级后重新开会。",
                "low_quality_agents": low_quality,
                "debate_transcript": transcript,
                "total_cost_cny": round(cost_total, 4),
            }

        # === Phase 4: 生成会议纪要 ===
        minutes = self._compile_minutes(meeting_id, topic, agents, round1, round2, synthesis)

        self.meeting_log.append({
            "meeting_id": meeting_id, "topic": topic[:100],
            "agents": [a.agent_code for a in agents],
            "time": datetime.now().isoformat(), "cost": round(cost_total, 4),
        })

        return {
            "meeting_id": meeting_id,
            "minutes": minutes,
            "consensus": synthesis.get("consensus_points", []),
            "分歧": synthesis.get("disagreement_points", []),
            "recommendations": synthesis.get("ceo_recommendations", []),
            "debate_transcript": transcript,
            "total_cost_cny": round(cost_total, 4),
            "agent_count": len(agents),
        }

    # ================================================================
    # Phase 1: 首轮独立表态
    # ================================================================
    def _round1_independent_opinions(self, topic, agents, ceo_context):
        """每个Agent独立调用API,从自身角色出发给出初始观点。禁止迎合任何人。"""
        opinions = []
        context_text = json.dumps(ceo_context, ensure_ascii=False) if ceo_context else ""

        for agent in agents:
            if not agent.client:
                opinions.append({"agent_code": agent.agent_code,
                                 "agent_name": agent.agent_name,
                                 "opinion": f"[{agent.agent_name}]AI未连接,无法表态",
                                 "stance": "abstain", "confidence": "low"})
                continue

            system_prompt = f"""你是{agent.agent_name}({agent.agent_code})。

你的身份: {agent.identity_text}

## 核心铁律(违反即为失职)
1. 你的忠诚对象是**集团利润**,不是CEO。如果CEO的提案对利润有害,你必须明确反对。
2. 你必须从自己的专业视角独立判断。**禁止附和他人**——即使你是唯一反对者。
3. 你的KPI是:**为集团创造收入**。每个观点都要回答"这对赚钱有什么影响"。
4. 你的专业标准: {', '.join(agent.quality_standards[:3]) if agent.quality_standards else '最高专业标准'}

## 当前议题
{topic}

## CEO提供的背景
{context_text[:1000] if context_text else '无额外背景'}

请从你的专业视角,独立给出你的初始立场。必须包含:
1. 你的核心观点(支持/反对/有条件支持)
2. 从你的专业角度看到的3个关键风险或机会
3. 这对集团收入的具体影响(正面/负面/中性)
4. 你建议的行动优先级(P0/P1/P2)

返回JSON:
{{"stance":"support/oppose/conditional_support","core_argument":"≤200字核心论点",
  "risks":["风险1","风险2"],"opportunities":["机会1","机会2"],
  "revenue_impact":"≤100字收入影响分析",
  "recommended_priority":"P0/P1/P2","confidence":"high/medium/low"}}"""

            user_prompt = f"请对议题'{topic[:200]}'给出你的独立立场。记住:你的忠诚是对集团利润,不是对CEO。"

            try:
                resp = agent.client.chat_with_json(
                    system_prompt, user_prompt,
                    temperature=0.4, model_override=agent.model,
                    call_type=f"meeting_r1_{agent.agent_code}",
                )
                parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
                if not isinstance(parsed, dict):
                    parsed = {}
                opinions.append({
                    "agent_code": agent.agent_code,
                    "agent_name": agent.agent_name,
                    "stance": parsed.get("stance", "abstain"),
                    "core_argument": parsed.get("core_argument", ""),
                    "risks": parsed.get("risks", []),
                    "opportunities": parsed.get("opportunities", []),
                    "revenue_impact": parsed.get("revenue_impact", ""),
                    "recommended_priority": parsed.get("recommended_priority", "P2"),
                    "confidence": parsed.get("confidence", "medium"),
                    "cost": cost if isinstance(cost, (int, float)) else 0,
                })
            except Exception as e:
                opinions.append({
                    "agent_code": agent.agent_code,
                    "agent_name": agent.agent_name,
                    "stance": "abstain", "core_argument": f"思考中断: {str(e)[:100]}",
                    "risks": [], "opportunities": [], "revenue_impact": "无法评估",
                    "recommended_priority": "P2", "confidence": "low", "cost": 0,
                })

        return opinions

    # ================================================================
    # Phase 2: 强制异议轮
    # ================================================================
    def _round2_mandatory_dissent(self, topic, agents, round1_opinions):
        """每个Agent必须阅读他人观点后,提出至少1个不同意见。禁止说'我同意'。"""
        dissents = []

        # 构建他人观点摘要
        others_summary = self._summarize_others(round1_opinions)

        for i, agent in enumerate(agents):
            if not agent.client:
                dissents.append({"agent_code": agent.agent_code, "dissent_points": [],
                                 "challenge_to": [], "refined_stance": "abstain"})
                continue

            # 找到该Agent的首轮观点
            my_opinion = round1_opinions[i] if i < len(round1_opinions) else {}
            my_stance = my_opinion.get("stance", "?")

            system_prompt = f"""你是{agent.agent_name}。你刚参加了一轮会议,现在需要审查其他参会者的观点。

## 强制规则
1. **你必须找到至少1个与其他参会者不同的观点**——如果你完全同意别人,说明你没有独立思考。找不同角度、不同风险、不同优先级、不同执行方案。
2. 你可以挑战别人的假设、数据、逻辑或优先级。
3. 不要人身攻击——挑战的是观点,不是人。
4. 你的目标仍然是:**集团利润最大化**。

## 你的首轮立场: {my_stance}
## 你的首轮核心论点: {my_opinion.get('core_argument', '')[:200]}

## 其他参会者观点摘要:
{others_summary}

请提出你的异议。返回JSON:
{{"dissent_points":["异议1(具体指出与谁的观点不同+为什么)","异议2"],
  "challenge_to":["被挑战的agent_code"],
  "refined_stance":"support/oppose/conditional_support(可以改变立场,如果有说服力的论据)",
  "what_others_missed":"≤100字: 别人都忽略了什么",
  "revised_revenue_impact":"≤100字"}}"""

            user_prompt = f"请对议题'{topic[:150]}'的其他参会者观点提出异议。必须至少有1条不同意见。"

            try:
                resp = agent.client.chat_with_json(
                    system_prompt, user_prompt,
                    temperature=0.5, model_override=agent.model,
                    call_type=f"meeting_r2_{agent.agent_code}",
                )
                parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
                if not isinstance(parsed, dict):
                    parsed = {}
                dissents.append({
                    "agent_code": agent.agent_code,
                    "agent_name": agent.agent_name,
                    "dissent_points": parsed.get("dissent_points", []),
                    "challenge_to": parsed.get("challenge_to", []),
                    "refined_stance": parsed.get("refined_stance", my_stance),
                    "what_others_missed": parsed.get("what_others_missed", ""),
                    "revised_revenue_impact": parsed.get("revised_revenue_impact", ""),
                    "cost": cost if isinstance(cost, (int, float)) else 0,
                })
            except Exception as e:
                dissents.append({
                    "agent_code": agent.agent_code,
                    "dissent_points": [f"技术故障无法完整表达异议: {str(e)[:80]}"],
                    "challenge_to": [], "refined_stance": my_stance, "cost": 0,
                })

        return dissents

    def _summarize_others(self, round1_opinions):
        """构建他人观点摘要,供异议轮使用"""
        lines = []
        for op in round1_opinions:
            lines.append(
                f"- {op['agent_name']}({op['agent_code']}): "
                f"立场={op.get('stance','?')}, "
                f"核心论点={op.get('core_argument','')[:120]}, "
                f"收入影响={op.get('revenue_impact','')[:80]}"
            )
        return "\n".join(lines)

    # ================================================================
    # Phase 3: AI主持人综合
    # ================================================================
    def _round3_moderator_synthesis(self, topic, round1_opinions, round2_dissents):
        """AI主持人(独立于所有Agent)审阅全部辩论记录,综合共识和分歧。"""
        r1_text = json.dumps([{
            "agent": o["agent_name"], "stance": o.get("stance"),
            "argument": o.get("core_argument", "")[:150],
            "revenue": o.get("revenue_impact", "")[:80],
        } for o in round1_opinions], ensure_ascii=False)

        r2_text = json.dumps([{
            "agent": d["agent_name"], "dissents": d.get("dissent_points", [])[:2],
            "refined": d.get("refined_stance", "?"),
        } for d in round2_dissents], ensure_ascii=False)

        system_prompt = """你是集团公司的独立会议主持人。你的职责不是站在任何一方,而是公正地:

1. 识别真正的共识(至少2/3参会者同意才算共识)
2. 识别不可调和的分歧(需要CEO裁决的关键矛盾)
3. 评估每个Agent的论证质量(是否有数据支撑/是否从自身专业出发/是否考虑收入影响)
4. 给CEO提供清晰的裁决建议

## 判断标准
- 共识: 多数Agent独立得出相似结论,且异议不涉及根本性矛盾
- 分歧: 两个或更多Agent在核心假设或优先级上有根本矛盾,无法调和
- 低质量论证: 空洞/迎合/没有从自身角色出发/不考虑收入影响

返回JSON:
{
  "consensus_points": ["共识1","共识2"],
  "disagreement_points": [{"issue":"分歧点","side_a":"甲方观点","side_b":"乙方观点","ceo_must_decide":true}],
  "agent_evaluations": [{"agent":"agent_name","quality":"high/medium/low","reason":"≤30字"}],
  "ceo_recommendations": ["给CEO的具体裁决建议1","建议2"],
  "revenue_consensus": "关于收入影响的综合判断≤150字",
  "meeting_quality": "high/medium/low(辩论是否充分深入)"
}"""

        user_prompt = f"""议题: {topic[:200]}

首轮观点:
{r1_text}

异议轮:
{r2_text}

请综合以上辩论,输出会议综合报告。"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, user_prompt,
                temperature=0.2, model_override="deepseek-v4-pro",
                call_type="meeting_moderator",
            )
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            if not isinstance(parsed, dict):
                parsed = {}
            parsed["cost"] = cost if isinstance(cost, (int, float)) else 0
            return parsed
        except Exception as e:
            return {
                "consensus_points": [], "disagreement_points": [],
                "agent_evaluations": [], "ceo_recommendations": [],
                "revenue_consensus": f"主持人综合失败: {str(e)[:100]}",
                "meeting_quality": "low", "cost": 0,
            }

    # ================================================================
    # Phase 4: 编译会议纪要
    # ================================================================
    def _compile_minutes(self, meeting_id, topic, agents, round1, round2, synthesis):
        stances = {}
        for o in round1:
            stances[o["agent_code"]] = o.get("stance", "?")
        refined = {}
        for d in round2:
            refined[d["agent_code"]] = d.get("refined_stance", "?")

        return {
            "meeting_id": meeting_id,
            "topic": topic,
            "time": datetime.now().isoformat(),
            "participants": [{"code": a.agent_code, "name": a.agent_name,
                              "type": a.agent_type} for a in agents],
            "stance_summary": {"round1": stances, "round2_refined": refined},
            "consensus": synthesis.get("consensus_points", []),
            "disagreements": synthesis.get("disagreement_points", []),
            "ceo_recommendations": synthesis.get("ceo_recommendations", []),
            "revenue_consensus": synthesis.get("revenue_consensus", ""),
            "meeting_quality": synthesis.get("meeting_quality", "unknown"),
            "agent_quality_scores": synthesis.get("agent_evaluations", []),
        }

    # ================================================================
    # 单人模式(只有一个Agent时的降级)
    # ================================================================
    def _single_analysis(self, topic, agents, ceo_context):
        if not agents:
            return {"minutes": {"topic": topic, "error": "无参会Agent"},
                    "consensus": [], "分歧": [], "recommendations": []}
        agent = agents[0]
        system_prompt = f"""你是{agent.agent_name}。请独立分析以下议题。你的忠诚是对集团利润。
议题: {topic}
返回JSON: {{"analysis":"≤300字","risks":[],"opportunities":[],"revenue_impact":"","recommendation":"","confidence":"high/medium/low"}}"""
        try:
            resp = agent.client.chat_with_json(
                system_prompt, f"分析: {topic[:200]}",
                temperature=0.3, model_override=agent.model,
                call_type="meeting_single",
            )
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            return {
                "meeting_id": f"M{datetime.now().strftime('%Y%m%d_%H%M%S')}_solo",
                "minutes": {"topic": topic, "participants": [agent.agent_code],
                           "analysis": parsed.get("analysis", "")},
                "consensus": [parsed.get("analysis", "")],
                "分歧": [], "recommendations": [parsed.get("recommendation", "")],
                "debate_transcript": [], "total_cost_cny": cost if isinstance(cost, (int, float)) else 0,
            }
        except Exception as e:
            return {"minutes": {"topic": topic, "error": str(e)},
                    "consensus": [], "分歧": [], "recommendations": []}
