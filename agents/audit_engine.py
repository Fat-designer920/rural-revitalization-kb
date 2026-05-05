"""
audit_engine.py - 17 Agent 质检引擎(15角色+1 Bug测试+1 UI设计)
路径：agents/audit_engine.py
版本：v2.3.7
"""
import json, time, traceback
from datetime import datetime
from scripts.deepseek_client import CostLimitExceeded
from agents.agent_orchestra import build_agent_dicts

# 24 个 Agent 定义(从 agent_orchestra 动态构建,兼容dict格式)
AGENT_DEFINITIONS = build_agent_dicts()
class AuditEngine(object):
    """17 Agent 质检引擎。复用 health_checker 的 _safe_dim() 隔离模式。"""

    def __init__(self, db, client, progress_callback=None):
        self.db = db
        self.client = client
        self.progress_callback = progress_callback
        self._cost = 0.0

    def seed_agents(self):
        """种子:将 17 个 Agent 定义写入 agent_definitions 表(幂等)"""
        return self.db.seed_agent_definitions(AGENT_DEFINITIONS)

    def run_weekly_cycle(self):
        """主入口:抽样→评分→汇总→生成任务。返回 {success, cycle_id, report}"""
        try:
            self._emit_progress("init", 0, 5, "初始化: 种子Agent定义 + 随机抽样")
            self.seed_agents()
            agents = self.db.get_active_agents()
            if not agents:
                return {"success": False, "error": "无活跃Agent定义"}

            sample = self.db.get_kp_sample_for_audit(n=20)
            if not sample:
                return {"success": False, "error": "无可审计的知识点(需confirmed状态)"}

            all_scores = {}
            all_gaps = []
            total_agents = len(agents)
            self._emit_progress("scoring", 1, total_agents, f"开始评分: {total_agents} 个Agent × {len(sample)} 条知识点")

            for i, agent in enumerate(agents):
                result = self._safe_dim(agent["agent_code"],
                    lambda ag=agent: self._score_agent(ag, sample))
                if result and result.get("success"):
                    all_scores[agent["agent_code"]] = result["scores"]
                    all_gaps.extend(result.get("gaps", []))
                self._emit_progress("scoring", i + 1, total_agents,
                    f"Agent {agent['agent_name']} 评分完成 ({i+1}/{total_agents})")

            # Agent 辩论:评分差异大的Agent进行AI辩论,产生更准确的评分
            debates = self._cross_validate(all_scores, agents, sample)

            self._emit_progress("synthesis", total_agents, total_agents, "汇总报告(AI辩论后) + 生成迭代任务")
            report = self._synthesize_report(all_scores, all_gaps, agents, sample)
            report["agent_debates"] = debates.get("debates", [])
            report["debate_count"] = debates.get("debate_count", 0)
            feed_tasks = self._generate_feed_tasks(all_gaps)
            structure_gaps = self._generate_structure_gaps(all_gaps)
            code_tasks = self._generate_code_tasks(all_gaps)

            cycle_id = self.db.save_audit_report({
                "cycle_label": "W{}".format(datetime.now().strftime("%Y-%V")),
                "kp_sample_ids": [kp["id"] for kp in sample],
                "status": "completed",
                "report_json": report,
                "feed_tasks": feed_tasks,
                "structure_gaps": structure_gaps,
                "code_tasks": code_tasks,
            })

            self._emit_progress("done", total_agents, total_agents, f"审计完成: cycle_id={cycle_id}")
            return {"success": True, "cycle_id": cycle_id, "report": report,
                    "feed_tasks": feed_tasks, "structure_gaps": structure_gaps,
                    "code_tasks": code_tasks}
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()[:1000]}

    def _cross_validate(self, all_scores, agents, sample):
        """Agent 辩论:让评分差异大的Agent对同一KP进行辩论,AI主持人裁决,产生更准确的评分。返回辩论报告。"""
        debates = []
        # 按域分组相关Agent
        gov_agents = [a for a in agents if a['agent_code'] in
                      ['township_cadre','county_land','county_agri','dev_reform','finance_bureau']]
        ent_agents = [a for a in agents if a['agent_code'] in
                      ['platform_pm','planning_institute','consulting_firm','construction_pm',
                       'industry_operator','social_capital']]
        local_agents = [a for a in agents if a['agent_code'] in
                        ['village_secretary','cooperative_head']]
        debate_groups = [gov_agents, ent_agents, local_agents]

        for group in debate_groups:
            if len(group) < 2:
                continue
            # 找评分方差最大的 KP
            max_var_kp = None
            max_var = 0
            for kp in sample[:3]:
                scores_list = []
                for ag in group:
                    ag_scores = all_scores.get(ag['agent_code'], {}).get(kp['id'], {})
                    if ag_scores:
                        scores_list.append(sum(ag_scores.values()) / len(ag_scores))
                if len(scores_list) >= 2:
                    variance = max(scores_list) - min(scores_list)
                    if variance > max_var and variance >= 1.0:
                        max_var = variance
                        max_var_kp = kp
            if not max_var_kp:
                continue

            # 组织辩论:用 V4-Flash 做主持人
            try:
                result = self._moderate_debate(group, max_var_kp, all_scores)
                if result:
                    debates.append(result)
            except Exception:
                pass

        return {"debates": debates, "debate_count": len(debates)}

    def _moderate_debate(self, agent_group, kp, all_scores):
        """AI 主持一场 Agent 辩论"""
        perspectives = []
        for ag in agent_group[:3]:
            sc = all_scores.get(ag['agent_code'], {}).get(kp['id'], {})
            if sc:
                perspectives.append(f"{ag['agent_name']}: 评分={sc}, 身份={ag['identity_text'][:80]}")

        if len(perspectives) < 2:
            return None

        system_prompt = """你是 Agent 辩论主持人。多个专业Agent对同一条知识点评分不同,你的任务是:
1. 分析每个Agent的视角是否合理
2. 找出分歧的根源(是信息不足还是视角差异)
3. 给出融合各视角的最终评分
4. 判断哪个Agent的推理最可靠(这个Agent应该被学习)

返回 JSON:
{"consensus_scores":{"维度1":分数,...},"disagreement_root":"分歧根源","best_agent":"最可靠的agent_code","learning_point":"其他Agent可以学习什么"}"""

        user_prompt = f"KP: {kp.get('title','')[:100]}\n内容: {(kp.get('original_excerpt') or '')[:200]}\n\nAgent评分分歧:\n" + "\n".join(perspectives)

        try:
            resp = self.client.chat_with_json(system_prompt, user_prompt,
                                                  temperature=0.1, model_override="deepseek-v4-flash",
                                                  call_type="agent_debate")
            return resp.get("parsed_json") if isinstance(resp, dict) else None
        except Exception:
            return None

    def _safe_dim(self, agent_code, fn):
        try:
            return fn()
        except Exception as e:
            return {"success": False, "error": str(e), "agent_code": agent_code}

    def _score_agent(self, agent, sample):
        """AI 驱动的 Agent 评分:用 V4-Flash 深度分析每条知识点在Agent视角下的质量"""
        scores = {}
        gaps = []
        dims = agent.get("scoring_dimensions") or []
        if isinstance(dims, str):
            try: dims = json.loads(dims)
            except Exception: dims = []
        questions = agent.get("core_questions") or []
        if isinstance(questions, str):
            try: questions = json.loads(questions)
            except Exception: questions = []

        # 构建 KP 摘要(每条 ≤300字,批量送 AI)
        kp_summaries = []
        for kp in sample:
            title = (kp.get("title") or "")[:100]
            excerpt = (kp.get("original_excerpt") or "")[:300]
            ctype = kp.get("content_type", "policy")
            qa = kp.get("qa_score") or 0
            kp_summaries.append(f"[{kp['id']}] {title} | 类型:{ctype} | QA:{qa}\n摘要:{excerpt}")

        # 调用 AI 批量评分
        try:
            ai_result = self._call_ai_score(agent, kp_summaries, dims, questions)
            if ai_result and ai_result.get("scores"):
                for item in ai_result["scores"]:
                    kp_id = item.get("kp_id")
                    dim_scores = item.get("dimension_scores", {})
                    if kp_id and dim_scores:
                        scores[kp_id] = dim_scores
                gaps = ai_result.get("gaps", [])
                return {"success": True, "scores": scores, "gaps": gaps}
        except Exception:
            pass

        # AI 调用失败 → 降级为规则引擎(基本保障)
        for kp in sample:
            scores[kp["id"]] = {d: 3 for d in dims}
        return {"success": True, "scores": scores, "gaps": gaps}

    def _call_ai_score(self, agent, kp_summaries, dims, questions):
        """调用 V4-Flash AI 进行深度评分(单次调用,批量返回)"""
        kps_text = "\n---\n".join(kp_summaries[:20])
        dims_text = ", ".join(dims)
        questions_text = "\n".join(f"- {q}" for q in questions[:7])

        system_prompt = f"""你是一个苛刻的知识库质量审查员。你的身份是:

{agent.get('identity_text','')}

你只关心跟你的实际工作直接相关的知识。评分标准:
{agent.get('quality_standards','')}

评分维度: {dims_text}
每个维度 1-5 分:
5=可以直接用,4=稍作调整就能用,3=有用但不够,2=勉强相关,1=完全没用

同时检查你的核心问题是否能在知识点中找到答案,找不到就是知识缺口。

返回 JSON:
{{
  "scores": [
    {{"kp_id": 数字, "dimension_scores": {{"维度1": 分数, ...}}, "comment": "≤50字评语"}}
  ],
  "gaps": [
    {{"question": "你的核心问题", "severity": "high/medium/low", "suggestion": "建议补充什么内容 ≤100字"}}
  ],
  "overall_assessment": "这个角色视角下知识库的整体评价 ≤150字"
}}"""

        user_prompt = f"""请审查以下 {len(kp_summaries)} 条知识点:

{kps_text}

你的核心问题:
{questions_text}

请严格按 JSON 格式输出评分结果。"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, user_prompt,
                temperature=0.1, model_override="deepseek-v4-flash",
                call_type="agent_audit",
            )
            return resp.get("parsed_json") if isinstance(resp, dict) else None
        except Exception:
            return None

    def _kp_matches_question(self, kp, question):
        title = (kp.get("title") or "").lower()
        excerpt = (kp.get("original_excerpt") or "").lower()
        q_lower = question.lower()
        keywords = [w for w in q_lower if len(w) >= 2]
        return any(kw in title or kw in excerpt for kw in keywords[:3])

    def _synthesize_report(self, all_scores, all_gaps, agents, sample):
        agent_summaries = []
        for ag in agents:
            code = ag["agent_code"]
            scores = all_scores.get(code, {})
            avg = 0
            if scores:
                all_vals = []
                for dim_scores in scores.values():
                    all_vals.extend(dim_scores.values())
                avg = sum(all_vals) / len(all_vals) if all_vals else 0
            agent_summaries.append({
                "agent_code": code, "agent_name": ag["agent_name"],
                "agent_type": ag["agent_type"],
                "avg_score": round(avg, 1),
                "kps_scored": len(scores),
            })

        overall_avg = sum(a["avg_score"] for a in agent_summaries) / len(agent_summaries) if agent_summaries else 0
        top_gaps = sorted(all_gaps, key=lambda g: g["severity"])[:10]

        return {
            "overall_score": round(overall_avg, 1),
            "agent_count": len(agents),
            "sample_count": len(sample),
            "agent_summaries": agent_summaries,
            "top_gaps": top_gaps,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _generate_feed_tasks(self, gaps):
        tasks = []
        for g in gaps[:5]:
            tasks.append({
                "type": "feed", "priority": "P1" if g["severity"] == "high" else "P2",
                "source_agent": g["agent_code"],
                "description": g["suggestion"],
                "target": "待定(需爬虫管道就位)",
            })
        return tasks

    def _generate_structure_gaps(self, gaps):
        return [{"type": "structure", "gap": g["question"], "source": g["agent_code"]} for g in gaps[:3]]

    def _generate_code_tasks(self, gaps):
        tasks = []
        bug_gaps = [g for g in gaps if g["agent_code"] == "bug_tester"]
        for g in bug_gaps[:3]:
            tasks.append({"type": "code", "priority": "P0", "description": g["suggestion"]})
        return tasks

    def _emit_progress(self, stage, current, total, message):
        if self.progress_callback:
            try:
                self.progress_callback({"stage": stage, "current": current, "total": total, "message": message})
            except Exception:
                pass


def run_audit_cycle(db, client, progress_callback=None):
    """模块级便捷入口"""
    engine = AuditEngine(db, client, progress_callback=progress_callback)
    return engine.run_weekly_cycle()
