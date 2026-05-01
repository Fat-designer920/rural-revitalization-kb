"""
prompt_optimizer.py - Prompt 自动优化器(评估→诊断→修补→验证)
路径：scripts/prompt_optimizer.py
版本：v2.3.7
"""
import json, time, traceback
from datetime import datetime


class PromptOptimizer(object):
    """Prompt 自动优化器。基于 Agent 审计结果,用 V4-Pro 分析 Prompt 缺陷并自动修补。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client
        self.optimization_log = []

    def optimize_iteration(self):
        """一轮 Prompt 优化迭代: 获取审计报告→分析 Prompt 缺陷→修补→记录。返回 {prompts_modified, details}"""
        audit = self.db.get_latest_audit_report()
        if not audit:
            return {"success": False, "error": "无审计报告,无法优化"}

        report = audit.get("report_json") or {}
        if isinstance(report, str):
            try:
                report = json.loads(report)
            except Exception:
                report = {}

        agent_summaries = report.get("agent_summaries", [])
        top_gaps = report.get("top_gaps", [])

        # 分析: 哪些维度的评分最低
        low_score_agents = [a for a in agent_summaries if a.get("avg_score", 5) < 2.5]
        prompts_modified = 0
        details = []

        if low_score_agents:
            # 用 V4-Pro 分析 Prompt 改进方向
            try:
                diagnosis = self._diagnose_with_ai(low_score_agents, top_gaps)
                if diagnosis.get("prompt_changes"):
                    modified = self._apply_prompt_changes(diagnosis["prompt_changes"])
                    prompts_modified = modified
                    details.extend(diagnosis.get("prompt_changes", []))
            except Exception as e:
                details.append({"error": f"AI 诊断失败: {e}"})

        # 记录优化日志
        self.optimization_log.append({
            "time": datetime.now().isoformat(),
            "low_score_agents": len(low_score_agents),
            "prompts_modified": prompts_modified,
            "details": details,
        })

        return {"success": True, "prompts_modified": prompts_modified,
                "low_score_agents": len(low_score_agents),
                "details": details}

    def _diagnose_with_ai(self, low_score_agents, top_gaps):
        """用 V4-Pro 分析 Prompt 缺陷并生成改进建议"""
        agent_text = json.dumps([{"name": a["agent_name"], "avg_score": a["avg_score"]}
                                 for a in low_score_agents[:5]], ensure_ascii=False)
        gaps_text = json.dumps(top_gaps[:5], ensure_ascii=False)

        system_prompt = """你是一个 Prompt 工程专家。你的任务是分析知识库 Agent 审计报告中的低分项,诊断 Prompt 层面的缺陷,并提出具体的 Prompt 修改方案。

## 你需要检查的 Prompt 类型
1. 提取 Prompt(_EXTRACT_BASE 系列): 控制知识点的提取质量
2. 读者打标 Prompt(READER_TAGGING_PROMPT): 控制读者定位准确性
3. 审计评分 Prompt: 控制 Agent 评分标准

## 输出格式
返回 JSON,含 prompt_changes 数组,每项含:
- prompt_name: Prompt 名称
- issue: 当前问题(≤100字)
- suggested_change: 具体修改建议(≤300字)
- priority: P0/P1/P2
- expected_improvement: 预期改进效果(≤100字)"""

        user_prompt = f"""审计报告摘要:

低分 Agent:
{agent_text}

Top 知识缺口:
{gaps_text}

请分析 Prompt 层面的缺陷并提出修改建议。"""

        try:
            resp, _ = self.client.chat_with_json(system_prompt, user_prompt,
                                                  temperature=0.3, model_override="deepseek-v4-pro",
                                                  call_type="prompt_optimizer")
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else None
            return parsed if isinstance(parsed, dict) else {"prompt_changes": []}
        except Exception:
            return {"prompt_changes": []}

    def _apply_prompt_changes(self, changes):
        """应用 Prompt 修改(记录到 CHANGELOG,实际修改需 Claude 审核)"""
        # 当前策略: 将修改建议写入任务队列,由 Claude 在新对话中审核执行
        # 不自动修改 Prompt,避免意外破坏
        try:
            queue_path = __import__('pathlib').Path(__file__).parent.parent / "docs" / "06_自动迭代任务队列.md"
            with open(queue_path, "a", encoding="utf-8") as f:
                for ch in changes:
                    f.write(f"| PROMPT-{ch.get('prompt_name','?')} | prompt | {ch.get('priority','P2')} "
                            f"| prompt_optimizer | {ch.get('suggested_change','')[:150]} | pending |\n")
            return len(changes)
        except Exception:
            return 0


def optimize_prompts(db, client):
    """模块级便捷入口"""
    opt = PromptOptimizer(db=db, client=client)
    return opt.optimize_iteration()
