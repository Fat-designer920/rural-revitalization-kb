"""
ceo_agent.py - CEO Agent: 自动化知识工厂总调度
路径：scripts/ceo_agent.py
版本：v2.3.7

职责: 感知知识库状态 → 决策下一步 → 调度各模块自动执行 → 从结果中学习 → 循环迭代
五大能力: 感知(Perceive) / 决策(Decide) / 执行(Execute) / 学习(Learn) / 报告(Report)
"""
import json, time, traceback
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# CEO 决策阈值
MIN_KPS_BEFORE_AUDIT = 50      # 至少 50 条知识点才开始审计
AUDIT_INTERVAL_MINUTES = 30    # 每 30 分钟自动审计一次
PROMPT_OPTIMIZE_THRESHOLD = 3.0  # 平均评分 < 此值时触发 Prompt 优化
MAX_LOOP_ITERATIONS = 50       # 最大循环迭代次数


class CEOAgent(object):
    """CEO Agent - 自动化知识工厂总调度。驱动完整的感知→决策→执行→学习循环。"""

    def __init__(self, db=None, client=None, headless=True):
        self.db = db
        self.client = client
        self.headless = headless
        self.cycle = 0
        self.log = []
        self.metrics = {"kps_fed": 0, "kps_extracted": 0, "audits_run": 0,
                        "prompts_optimized": 0, "bugs_fixed": 0, "crawl_cycles": 0}
        self._consecutive_failures = 0
        self._last_action = None
        self._last_result_ok = True
        self._stagnation_counter = 0
        self._last_kps_count = 0
        self._last_audit_score = 0

    # ================================================================
    # 主循环
    # ================================================================
    def run(self, max_iterations=MAX_LOOP_ITERATIONS):
        """启动 CEO 自动化主循环。返回最终报告。"""
        self._log("CEO Agent 启动", "info", f"最大迭代={max_iterations}")
        self._ensure_imports()

        for i in range(max_iterations):
            self.cycle = i + 1

            # === 死循环防护 ===
            if self._consecutive_failures >= 5:
                self._log("熔断", "error", f"连续失败 {self._consecutive_failures} 次,触发熔断保护")
                break
            if self._stagnation_counter >= 8:
                self._log("停滞", "warning", f"连续 {self._stagnation_counter} 轮无改进,暂停循环")
                break

            self._log("循环开始", "info", f"第 {self.cycle}/{max_iterations} 轮")

            # 1. 感知
            state = self._perceive()

            # 2. 决策(避免重复相同失败动作)
            action = self._decide(state)
            if action == self._last_action and not self._last_result_ok:
                self._log("避重", "warning", f"跳过重复失败动作: {action}")
                action = self._fallback_action(state)

            # 3. 执行
            result = self._execute(action)
            self._last_action = action
            self._last_result_ok = result and result.get("success")

            # 4. 学习 + 更新熔断
            self._learn(action, result)

            # 5. 停滞检测
            self._detect_stagnation(state)

            # 6. 报告
            self._report(state, action, result)

            # 7. 终止条件
            if action == "idle" and state["audit_avg_score"] >= 4.0:
                self._log("收敛", "info", "知识库评分达标,循环结束")
                break
            if state["kps_total"] >= 10000:
                self._log("规模达标", "info", "KPs>=10000,暂停自动循环")
                break

            # 8. 冷却: 避免 API 过热
            time.sleep(2)

        return self._final_report()

    # ================================================================
    # 1. 感知
    # ================================================================
    def _perceive(self):
        """扫描知识库状态,返回结构化快照"""
        state = {"kps_total": 0, "kps_confirmed": 0, "kps_with_reader_tags": 0,
                 "audit_avg_score": 0, "latest_audit": None, "qa_quality": 0,
                 "pending_files": 0, "crawl_queue": 0, "prompt_version": ""}

        try:
            stats = self.db.get_statistics()
            state["kps_total"] = (stats.get("knowledge_points", {}) or {}).get("cnt", 0)
        except Exception:
            pass

        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed'")
            state["kps_confirmed"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM knowledge_points WHERE target_reader!='[]' AND target_reader IS NOT NULL AND target_reader!=''")
            state["kps_with_reader_tags"] = c.fetchone()[0]
            conn.close()
        except Exception:
            pass

        state["latest_audit"] = self.db.get_latest_audit_report()
        if state["latest_audit"]:
            rj = state["latest_audit"].get("report_json") or {}
            if isinstance(rj, str):
                try:
                    rj = json.loads(rj)
                except Exception:
                    rj = {}
            state["audit_avg_score"] = rj.get("overall_score", 0)

        try:
            from scripts.prompts.prompt_templates import PROMPT_VERSION
            state["prompt_version"] = PROMPT_VERSION
        except Exception:
            pass

        try:
            pending_dir = PROJECT_ROOT / "data" / "pending"
            state["pending_files"] = len(list(pending_dir.glob("*"))) if pending_dir.exists() else 0
        except Exception:
            pass

        try:
            test_dir = PROJECT_ROOT / "测试用文件" / "乡村振兴资料库"
            state["test_files_available"] = len(list(test_dir.rglob("*"))) if test_dir.exists() else 0
        except Exception:
            pass

        return state

    # ================================================================
    # 2. 决策(AI 驱动)
    # ================================================================
    def _decide(self, state):
        """AI 驱动的战略决策:用 V4-Flash 分析状态→决定最优动作"""
        # 硬约束(不需要 AI): 无知识点时先喂料
        if state["kps_confirmed"] < 10:
            return "feed_test_files" if state.get("test_files_available", 0) > 0 else "crawl"

        # AI 决策: 让 AI 根据完整状态选择最优动作
        try:
            action = self._ai_decide(state)
            if action in ["feed_test_files", "audit", "optimize_prompt",
                          "backfill_reader_tags", "crawl", "test_qa_quality", "idle"]:
                return action
        except Exception:
            pass

        # AI 不可用时的降级规则
        if state["kps_confirmed"] < MIN_KPS_BEFORE_AUDIT:
            return "feed_test_files"
        if state["kps_with_reader_tags"] < state["kps_confirmed"] * 0.5:
            return "backfill_reader_tags"
        if self.cycle % 5 == 0:
            return "audit"
        return "idle"

    def _ai_decide(self, state):
        """调用 V4-Flash 做 CEO 级别战略决策"""
        state_text = json.dumps({
            "cycle": self.cycle,
            "kps_confirmed": state["kps_confirmed"],
            "kps_with_reader_tags": state["kps_with_reader_tags"],
            "audit_avg_score": state["audit_avg_score"],
            "pending_files": state.get("pending_files", 0),
            "test_files_available": state.get("test_files_available", 0),
            "consecutive_failures": self._consecutive_failures,
            "stagnation_counter": self._stagnation_counter,
            "metrics": self.metrics,
        }, ensure_ascii=False)

        system_prompt = """你是乡村振兴知识工厂的 CEO。你需要根据当前状态做出最优决策。

可选动作:
- feed_test_files: 喂入测试用文件,扩充知识库
- audit: 运行 Agent 审计,评估知识库质量
- optimize_prompt: 根据审计结果优化 Prompt
- backfill_reader_tags: 回填读者定位标签
- crawl: 触发爬虫抓取新内容
- test_qa_quality: 测试问答助手质量
- idle: 本轮不动作,等待下次循环

决策原则:
1. 知识库 <50条 且有待喂文件 → feed_test_files
2. 读者标签覆盖率 <50% → backfill_reader_tags
3. 每5轮至少审计一次
4. 审计评分 <3.0 → optimize_prompt
5. 连续失败 ≥3 → idle 或换策略
6. 停滞 ≥5轮 → 尝试新策略(crawl/test_qa_quality)

返回 JSON: {"action": "动作", "reason": "≤100字理由"}"""

        user_prompt = f"当前状态:\n{state_text}\n\n请做出 CEO 决策,返回 JSON。"

        try:
            resp, _ = self.client.chat_with_json(
                system_prompt, user_prompt,
                temperature=0.2, model_override="deepseek-v4-flash",
                call_type="ceo_decide",
            )
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else None
            return parsed.get("action", "idle") if isinstance(parsed, dict) else "idle"
        except Exception:
            return "idle"

    # ================================================================
    # 3. 执行
    # ================================================================
    def _execute(self, action):
        """执行决策动作,返回结果"""
        self._log("执行", "info", f"动作={action}")
        if action == "feed_test_files":
            return self._action_feed_test_files()
        elif action == "audit":
            return self._action_run_audit()
        elif action == "optimize_prompt":
            return self._action_optimize_prompt()
        elif action == "backfill_reader_tags":
            return self._action_backfill_reader_tags()
        elif action == "crawl":
            return self._action_crawl()
        elif action == "test_qa_quality":
            return self._action_test_qa_quality()
        return {"action": action, "status": "skipped"}

    def _action_feed_test_files(self):
        """批量喂入测试用文件: 拷贝到 pending/ → 预处理 → 提取"""
        try:
            from scripts.auto_feeder import AutoFeeder
            feeder = AutoFeeder(db=self.db, client=self.client)
            result = feeder.feed_all_test_files()
            self.metrics["kps_fed"] += result.get("files_processed", 0)
            self.metrics["kps_extracted"] += result.get("kps_extracted", 0)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _action_run_audit(self):
        """运行 Agent 审计周期"""
        try:
            from scripts.audit_engine import run_audit_cycle
            result = run_audit_cycle(self.db, self.client)
            self.metrics["audits_run"] += 1
            # 审计完成后自动写入任务队列
            if result.get("success") and result.get("code_tasks"):
                self._write_task_queue(result)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _action_optimize_prompt(self):
        """自动优化 Prompt: 用 V4-Pro 分析审计结果→优化 Prompt→验证"""
        try:
            from scripts.prompt_optimizer import PromptOptimizer
            opt = PromptOptimizer(db=self.db, client=self.client)
            result = opt.optimize_iteration()
            self.metrics["prompts_optimized"] += result.get("prompts_modified", 0)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _action_backfill_reader_tags(self):
        """回填读者定位标签"""
        try:
            from scripts.reader_tagger import run_reader_backfill
            return run_reader_backfill(self.db, self.client, batch_size=100)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _action_crawl(self):
        """触发爬虫抓取"""
        try:
            from scripts.crawler_scheduler import CrawlerScheduler
            crawler = CrawlerScheduler(db=self.db)
            result = crawler.run_scheduled(schedule="daily")
            self.metrics["crawl_cycles"] += 1
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _action_test_qa_quality(self):
        """测试问答质量: 用 Agent 的核心问题测试 QA 系统"""
        results = []
        try:
            from scripts.audit_engine import AGENT_DEFINITIONS
            from scripts.qa_assistant import run_qa
            test_questions = []
            for ag in AGENT_DEFINITIONS[:5]:
                qs = ag.get("core_questions") or []
                if isinstance(qs, str):
                    try:
                        qs = json.loads(qs)
                    except Exception:
                        qs = []
                test_questions.extend(qs[:2])
            for q in test_questions[:10]:
                try:
                    ans = run_qa(self.db, self.client, q)
                    results.append({"question": q, "has_answer": bool(ans and ans.get("answer_json"))})
                except Exception:
                    results.append({"question": q, "error": "QA 调用失败"})
            return {"success": True, "questions_tested": len(results), "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ================================================================
    # 4. 学习
    # ================================================================
    def _learn(self, action, result):
        """从执行结果中学习,更新决策策略"""
        ok = result and result.get("success")
        if ok:
            self._consecutive_failures = 0
            self._log("学习", "info", f"{action} 成功")
        else:
            self._consecutive_failures += 1
            err = result.get("error", "?") if result else "None"
            self._log("学习", "warning", f"{action} 失败({self._consecutive_failures}/5): {err}")

    def _detect_stagnation(self, state):
        """检测是否停滞:连续N轮无KPs增长且评分无提升"""
        current_kps = state.get("kps_confirmed", 0)
        current_score = state.get("audit_avg_score", 0)
        if current_kps == self._last_kps_count and abs(current_score - self._last_audit_score) < 0.1:
            self._stagnation_counter += 1
        else:
            self._stagnation_counter = 0
        self._last_kps_count = current_kps
        self._last_audit_score = current_score

    def _fallback_action(self, state):
        """当前动作失败后的备用动作"""
        if state.get("pending_files", 0) > 0:
            return "feed_test_files"
        return "audit" if state["kps_confirmed"] >= MIN_KPS_BEFORE_AUDIT else "idle"

    # ================================================================
    # 5. 报告
    # ================================================================
    def _report(self, state, action, result):
        """输出本轮进度报告"""
        msg = (f"[CEO-{self.cycle:03d}] {action:25s} | "
               f"KPs:{state['kps_confirmed']:5d} | "
               f"Audit:{state['audit_avg_score']:.1f} | "
               f"Readers:{state['kps_with_reader_tags']:5d} | "
               f"Result:{'OK' if result and result.get('success') else 'FAIL'}")
        print(msg)
        self.log.append({"cycle": self.cycle, "action": action, "state": state,
                         "result_summary": str(result)[:200], "time": datetime.now().isoformat()})

    def _final_report(self):
        return {"cycles_completed": self.cycle, "metrics": self.metrics,
                "log": self.log[-20:], "conclusion": "CEO 循环结束"}

    # ================================================================
    # 工具
    # ================================================================
    def _ensure_imports(self):
        """确保核心模块可导入"""
        if self.db is None:
            from scripts.db_manager import DatabaseManager
            self.db = DatabaseManager()
        if self.client is None:
            from scripts.deepseek_client import DeepSeekClient
            self.client = DeepSeekClient()

    def _log(self, stage, level, msg):
        entry = f"[CEO] {stage}: {msg}"
        print(entry)
        try:
            if self.db:
                self.db.log_operation_event(event_type=f"ceo_{stage}", severity=level,
                                            module="ceo_agent", payload={"msg": msg})
        except Exception:
            pass

    def _write_task_queue(self, audit_result):
        """将审计结果写入自动迭代任务队列"""
        try:
            queue_path = PROJECT_ROOT / "docs" / "06_自动迭代任务队列.md"
            tasks = audit_result.get("code_tasks") or []
            if not tasks:
                return
            with open(queue_path, "a", encoding="utf-8") as f:
                for t in tasks[:5]:
                    t_id = f"A{int(time.time()) % 10000:04d}"
                    f.write(f"| {t_id} | {t.get('type','code')} | {t.get('priority','P2')} "
                            f"| {t.get('source_agent','ceo')} | {t.get('description','')} | pending |\n")
        except Exception:
            pass


def main():
    """CLI 入口: 启动 CEO Agent 自动化循环"""
    print("=" * 60)
    print("  CEO Agent v2.3.7 — 自动化知识工厂总调度")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    ceo = CEOAgent(headless=True)
    report = ceo.run(max_iterations=MAX_LOOP_ITERATIONS)
    print(f"\n  CEO 最终报告: {json.dumps(report['metrics'], ensure_ascii=False)}")
    return report


if __name__ == "__main__":
    main()
