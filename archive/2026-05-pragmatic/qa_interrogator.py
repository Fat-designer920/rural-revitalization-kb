"""
qa_interrogator.py - 知识库审问Agent(真Agent, 不是固化的测试脚本)
路径：agents/qa_interrogator.py
版本：v2.3.7-part2

不是一个拨号机器人。是一个有独立判断力的审问者。
会自己思考该问什么、会追问、会苛刻验证、会找到知识库最薄弱的环节。
"""
import json, time, sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "agents"))

from base_agent import BaseAgent


class QAInterrogator(BaseAgent):
    """知识库审问Agent。以操盘手视角对KB进行严苛审问。

    不是"跑20个固定问题"的测试脚本。而是:
    1. 先研究——理解课程体系+客户画像+KB现状
    2. 再思考——自主决定该问什么、怎么追问
    3. 后审问——层层递进,答案不够好就追着打
    4. 最终判——给出KB是否可用的诚实判断
    """

    def __init__(self, client=None, db=None):
        super().__init__(
            agent_code="qa_interrogator",
            agent_name="知识库审问Agent",
            agent_type="role",
            identity_text=(
                "我是知识库审问Agent。我的职责是用最苛刻的标准测试知识库的问答能力。"
                "我会像真实的乡村振兴操盘手一样提问——他们会问得具体、追问得深入、"
                "对模棱两可的回答零容忍。我不会走过场,不会为了'测试通过'而放水。"
                "我的核心信念: 如果知识库经不起我的审问,它就不配给真正的操盘手用。"
            ),
            core_questions=[
                "知识库能否回答操盘手的真实问题,而不仅仅是政策复述?",
                "回答里的数据、案例、政策引用是否经得起核实?",
                "知识的盲区在哪里?哪些操盘手必问的问题KB完全答不了?",
                "KB的回答是'百度百科风格'还是'20年老师傅风格'?",
            ],
            quality_standards=[
                "回答必须有具体数据或案例支撑,不能空谈框架",
                "回答必须接地气——操盘手看完知道下一步该干什么",
                "回答必须诚实——不知道就直说不知道,不能装懂",
                "引用必须可追溯——不能出现'据相关文件'这类模糊表述",
            ],
            scoring_dimensions=[
                "实用性(看完能用吗)", "准确性(数据和政策对吗)",
                "深度(是表面回答还是深层洞察)", "诚实度(有没有暴露知识盲区)",
            ],
            client=client, db=db, model="deepseek-v4-pro",
        )
        self.interrogation_log = []
        self.weaknesses_found = []
        self.strong_points = []

    # ================================================================
    # 主流程: 完整审问
    # ================================================================
    def interrogate(self, num_rounds=10):
        """对知识库进行严苛审问。返回完整审问报告。

        流程:
        1. 研究阶段: 分析KB现状, 确定审问重点
        2. 审问阶段: 逐轮提问→追问→深挖
        3. 判决阶段: 给出诚实结论
        """
        report = {
            "interrogation_id": f"INT-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "started_at": datetime.now().isoformat(),
            "kb_state": self._snapshot_kb(),
            "phases": {},
        }

        # Phase 1: 研究
        study = self._phase_study()
        report["phases"]["study"] = study

        # Phase 2: 审问
        rounds = self._phase_interrogate(study, num_rounds)
        report["phases"]["rounds"] = rounds

        # Phase 3: 判决
        verdict = self._phase_verdict(rounds)
        report["phases"]["verdict"] = verdict

        report["completed_at"] = datetime.now().isoformat()
        return report

    # ================================================================
    # Phase 1: 研究——自主决定审问方向
    # ================================================================
    def _phase_study(self):
        """分析KB现状,确定该审问什么。这是Agent的'思考'阶段。"""
        kb = self._snapshot_kb()

        # 用AI分析策略
        context = {
            "task": "审问策略制定",
            "kb_state": kb,
            "guidance": (
                "基于KB现状,设计审问策略。重点关注:\n"
                "1. KB最弱的领域(按content_type分布找)\n"
                "2. 课程体系20课中哪些课KB覆盖最差\n"
                "3. 操盘手最关心的5类问题(资金/政策/案例/方法/风险)\n"
                "4. 应该问什么类型的问题?具体怎么问?\n"
                "返回: {strategy_summary, focus_areas, question_types, specific_questions}"
            ),
        }
        analysis = self.think(context, deep=True)
        return analysis

    # ================================================================
    # Phase 2: 审问——提问+追问+深挖
    # ================================================================
    def _phase_interrogate(self, study, num_rounds):
        """执行多轮审问。每轮: 生成问题→提问→评估→如果不满意就追问。"""
        from qa_assistant import run_qa as qa_run

        rounds = []
        topics_covered = set()

        # 从研究中提取初始问题方向
        initial_angles = self._derive_angles(study)

        for rnd in range(num_rounds):
            # 选择本轮审问角度
            if rnd < len(initial_angles):
                angle = initial_angles[rnd]
            else:
                # 后续轮次: 基于前面发现的弱点追问
                angle = self._pick_followup_angle(rounds, topics_covered)

            # 生成具体问题(用AI思考)
            question = self._generate_question(angle, rounds, topics_covered)
            topics_covered.add(angle.get("topic", ""))

            # 提问
            t0 = time.time()
            resp = qa_run(db=self.db, client=self.client,
                         query=question, mode="self", is_test_query=1)
            latency = time.time() - t0

            # 评估回答质量
            evaluation = self._evaluate_answer(question, resp, angle)

            round_result = {
                "round": rnd + 1,
                "angle": angle,
                "question": question,
                "answer_summary": self._extract_answer_summary(resp),
                "source": resp.get("source", "unknown"),
                "latency_ms": resp.get("latency_ms", 0),
                "evaluation": evaluation,
            }

            # 如果不满意, 追问
            if evaluation.get("score", 0) < 60 and rnd < num_rounds - 1:
                followup = self._generate_followup(question, resp, evaluation)
                if followup:
                    t0 = time.time()
                    fu_resp = qa_run(db=self.db, client=self.client,
                                   query=followup, mode="self", is_test_query=1)
                    fu_latency = time.time() - t0
                    fu_eval = self._evaluate_answer(followup, fu_resp, angle)
                    round_result["followup"] = {
                        "question": followup,
                        "answer_summary": self._extract_answer_summary(fu_resp),
                        "source": fu_resp.get("source", "unknown"),
                        "evaluation": fu_eval,
                    }

            rounds.append(round_result)

            if evaluation.get("score", 0) < 30:
                self.weaknesses_found.append({
                    "angle": angle,
                    "question": question,
                    "reason": evaluation.get("critique", ""),
                })
            elif evaluation.get("score", 0) >= 70:
                self.strong_points.append({
                    "angle": angle,
                    "reason": evaluation.get("strength", ""),
                })

            time.sleep(1)  # 限速

        return rounds

    # ================================================================
    # Phase 3: 判决
    # ================================================================
    def _phase_verdict(self, rounds):
        """给出最终判决。不为面子放水。"""
        scores = [r["evaluation"].get("score", 0) for r in rounds]
        # 含追问的也要算
        for r in rounds:
            if r.get("followup") and r["followup"].get("evaluation"):
                scores.append(r["followup"]["evaluation"].get("score", 0))

        avg_score = sum(scores) / max(1, len(scores))
        pass_count = sum(1 for s in scores if s >= 60)

        verdict_level = "不合格"
        if avg_score >= 80:
            verdict_level = "合格——可以面向操盘手提供问答服务"
        elif avg_score >= 60:
            verdict_level = "勉强可用——需要补强后再上线"
        elif avg_score >= 40:
            verdict_level = "不可用——知识库存在严重缺口,需大量喂料"

        return {
            "average_score": round(avg_score, 1),
            "total_checks": len(scores),
            "pass_count": pass_count,
            "pass_rate": f"{100*pass_count//max(1,len(scores))}%",
            "verdict": verdict_level,
            "weaknesses": self.weaknesses_found[:5],
            "strong_points": self.strong_points[:5],
            "feed_priority": self._derive_feed_priorities(),
        }

    # ================================================================
    # 辅助方法
    # ================================================================
    def _snapshot_kb(self):
        if not self.db:
            return {}
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM knowledge_points")
            total = c.fetchone()[0]
            c.execute("""SELECT content_type, COUNT(*) FROM knowledge_points
                         WHERE review_status='confirmed' GROUP BY content_type""")
            by_type = dict(c.fetchall())
            c.execute("""SELECT content_readiness, COUNT(*) FROM knowledge_points
                         WHERE review_status='confirmed' GROUP BY content_readiness""")
            by_readiness = dict(c.fetchall())
            c.execute("SELECT AVG(qa_score) FROM knowledge_points WHERE qa_score>0")
            avg_qa = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM source_files WHERE process_status='completed'")
            files = c.fetchone()[0]
            conn.close()
            return {"total_kps": total, "by_type": by_type,
                    "by_readiness": by_readiness, "avg_qa_score": round(avg_qa, 2) if avg_qa else 0,
                    "files_processed": files}
        except Exception:
            return {}

    def _derive_angles(self, study):
        """从研究结果中提取审问角度。"""
        specific = study.get("specific_questions", []) if isinstance(study, dict) else []
        if specific:
            return [{"topic": q[:30], "question": q} for q in specific[:10]]

        # 默认角度(如果AI没给)
        return [
            {"topic": "资金", "question": "做乡村振兴项目最靠谱的融资渠道是什么?专项债和银行贷款各有什么优劣?"},
            {"topic": "政策", "question": "全域土地综合整治最新的政策窗口是什么?2025-2026年有什么新变化?"},
            {"topic": "风险", "question": "乡村振兴项目最常见的失败原因是什么?具体踩过什么坑?"},
            {"topic": "策划", "question": "一个乡村振兴项目从0到1,第一步该做什么?怎么判断能不能做?"},
            {"topic": "案例", "question": "四川做得最好的乡村振兴项目是哪些?能具体说说怎么做的吗?"},
            {"topic": "指标", "question": "建设用地指标怎么交易?增减挂钩指标现在什么行情?流程是什么?"},
            {"topic": "实施", "question": "高标准农田建设项目从申报到验收,最容易在哪个环节卡住?"},
            {"topic": "运营", "question": "项目建好了怎么运营才能赚钱?合作社怎么管才不会乱?"},
            {"topic": "方法", "question": "跟政府领导汇报项目方案,什么该说什么不该说?有没有具体话术?"},
            {"topic": "退出", "question": "社会资本参与乡村振兴项目,最后怎么退出?REITs能走通吗?"},
        ]

    def _pick_followup_angle(self, previous_rounds, covered):
        """基于前面发现的弱点,选择新的审问角度。"""
        if self.weaknesses_found:
            # 继续攻击薄弱点
            weak = self.weaknesses_found[-1]
            return {"topic": f"深挖:{weak['angle'].get('topic','')}",
                   "context": weak.get("reason", "")}
        # 随机选一个没覆盖的
        all_topics = ["资金", "政策", "风险", "策划", "案例", "指标", "实施", "运营", "方法", "退出"]
        for t in all_topics:
            if t not in covered:
                return {"topic": t, "question": f"关于{t}方面,还有什么操盘手必须知道但KB可能没有的?"}
        return {"topic": "综合", "question": "做一个乡村振兴项目,最关键的三个成功因素是什么?"}

    def _generate_question(self, angle, history, covered):
        """生成具体审问问题。用AI思考确保问题质量。"""
        # 如果有预定义问题直接用
        if angle.get("question"):
            return angle["question"]

        # 否则用AI生成
        context = {
            "angle": angle,
            "previous_weaknesses": [w["reason"][:100] for w in self.weaknesses_found[-3:]],
            "topics_covered": list(covered),
            "instruction": "生成一个具体的、犀利的审问问题。要像操盘手真实会问的问题,不要学术腔。"
        }
        result = self.think(context, deep=False)
        if isinstance(result, dict) and result.get("question"):
            return result["question"]
        return f"关于{angle.get('topic','乡村振兴')},操盘手最需要知道什么?"

    def _generate_followup(self, original_q, resp, evaluation):
        """生成追问。对答案不满意就追着打。"""
        answer_text = self._extract_answer_summary(resp)
        context = {
            "original_question": original_q,
            "answer_received": answer_text[:500],
            "evaluation": evaluation,
            "instruction": (
                "这个回答不够好。请生成一个犀利的追问,逼它给出更具体的答案。"
                "追问应该: 1)指出原回答的模糊之处 2)要求具体数据/案例 3)语气像真的操盘手在追问"
                "返回: {question: 追问内容}"
            ),
        }
        result = self.think(context, deep=False)
        if isinstance(result, dict) and result.get("question"):
            return result["question"]
        # Fallback: 通用追问
        return f"你刚刚说的太笼统了,能不能举个具体的例子?数字是多少?"

    def _evaluate_answer(self, question, resp, angle):
        """苛刻评估回答质量。使用独立AI调用(不用think,因为需要自定义输出格式)。"""
        answer_text = self._extract_answer_summary(resp)

        # 快速硬指标
        source = resp.get("source", "rule_fallback")
        if source == "rule_fallback":
            return {"score": 0, "critique": "问答走rule_fallback,KB无法检索到相关知识",
                    "strength": "", "pass": False}

        answer_panels = resp.get("answer") or {}
        evidence_count = len(answer_panels.get("evidence_kp_ids", [])) if isinstance(answer_panels, dict) else 0
        coverage_gap = answer_panels.get("coverage_gap", "") if isinstance(answer_panels, dict) else ""

        # 用独立AI调用做苛刻评估(需要自定义JSON输出格式, think()的固定格式不够)
        if self.client:
            try:
                sp = (
                    "你是知识库质量审计官。用最苛刻的标准评估问答质量。不为面子放水。\n"
                    "评估维度:\n"
                    "1. 实用性(0-30): 操盘手看完知道下一步该干什么?\n"
                    "2. 准确性(0-25): 数据和政策引用经得起核实?\n"
                    "3. 深度(0-25): 是百度百科还是20年老师傅?\n"
                    "4. 诚实度(0-20): 不知道有没有说不知道?\n"
                    "只返回JSON,不要其他内容。"
                )
                up = (
                    f"问题: {question}\n"
                    f"回答: {answer_text[:600]}\n"
                    f"Evidence数: {evidence_count}\n"
                    f"知识盲区: {coverage_gap[:200]}\n"
                    f"角度: {angle.get('topic','')}\n\n"
                    f"请苛刻评分。返回JSON: "
                    f'{{"total_score":0-100,"usefulness":0-30,"accuracy":0-25,'
                    f'"depth":0-25,"honesty":0-20,'
                    f'"critique":"扣分原因(≤100字)","strength":"亮点(如有,≤50字)","pass":true/false}}'
                )
                resp_json = self.client.chat_with_json(
                    sp, up, temperature=0.2, model_override="deepseek-v4-flash",
                    call_type="qa_evaluate",
                )
                parsed = resp_json.get("parsed_json") if isinstance(resp_json, dict) else {}
                if isinstance(parsed, dict) and "total_score" in parsed:
                    return {
                        "score": parsed.get("total_score", 50),
                        "usefulness": parsed.get("usefulness", 0),
                        "accuracy": parsed.get("accuracy", 0),
                        "depth": parsed.get("depth", 0),
                        "honesty": parsed.get("honesty", 0),
                        "critique": parsed.get("critique", ""),
                        "strength": parsed.get("strength", ""),
                        "pass": parsed.get("pass", False),
                    }
            except Exception:
                pass

        # Fallback评分(规则)
        score = 50
        if evidence_count >= 2: score += 15
        if coverage_gap: score += 10
        if source == "main": score += 10
        if source in ("r1_fallback",): score -= 20
        return {"score": max(0, min(100, score)),
                "critique": "评估调用失败,降级为规则评分(非AI判断)",
                "strength": "", "pass": score >= 60}

    def _extract_answer_summary(self, resp):
        """从QA响应中提取回答文本。"""
        answer_panels = resp.get("answer")
        if isinstance(answer_panels, dict):
            return answer_panels.get("direct_answer", "") or ""
        if isinstance(answer_panels, str):
            return answer_panels[:500]
        return str(answer_panels)[:300] if answer_panels else "(无回答)"

    def _derive_feed_priorities(self):
        """从审问弱点反推喂料优先级。"""
        priorities = {}
        for w in self.weaknesses_found:
            topic = w.get("angle", {}).get("topic", "未知") if isinstance(w.get("angle"), dict) else "未知"
            priorities[topic] = priorities.get(topic, 0) + 1
        return sorted(priorities.items(), key=lambda x: x[1], reverse=True)

    # ================================================================
    # 一键审问(模块级入口)
    # ================================================================
    def quick_interrogate(self):
        """快速审问(5轮), 用于运营检查。"""
        return self.interrogate(num_rounds=5)

    def deep_interrogate(self):
        """深度审问(15轮), 用于重大版本发布前。"""
        return self.interrogate(num_rounds=15)

    def to_dict(self):
        return {
            "agent_code": self.agent_code,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "identity_text": self.identity_text,
            "core_questions": self.core_questions,
            "quality_standards": self.quality_standards,
        }


def run_interrogation(client=None, db=None, deep=False):
    """模块级便捷入口。"""
    interrogator = QAInterrogator(client=client, db=db)
    return interrogator.deep_interrogate() if deep else interrogator.quick_interrogate()
