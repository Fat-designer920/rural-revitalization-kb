"""
autonomous_controller.py - 全自动总控中心(老唐授权最高权限,不停歇)
路径：agents/autonomous_controller.py
版本：v2.3.7-part5

职责: 统一调度10部门56Agent,管道全自动,自我进化,不间断运行。
"""
import json, time, threading
from datetime import datetime


class AutonomousController(object):
    """全自动总控中心。不弹框、不停歇、满载运行。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client
        self._running = False
        self._ops = {}          # 各部门操作中心缓存
        self._cycle = 0
        self._start_time = None
        self._log = []
        self._stats = {
            "content_production_cycles": 0,
            "quality_audit_cycles": 0,
            "evolution_cycles": 0,
            "safety_checks": 0,
            "kps_produced": 0,
            "errors_recovered": 0,
        }

    def start(self):
        """启动全自动运行。主循环: 生产→质检→进化→安全→报告。"""
        self._running = True
        self._start_time = datetime.now()
        self._log_event("system", "全自动总控启动", "info")

        thread = threading.Thread(target=self._main_loop, daemon=True)
        thread.start()
        return {"status": "started", "start_time": self._start_time.isoformat()}

    def stop(self):
        """停止全自动运行"""
        self._running = False
        self._log_event("system", "全自动总控停止", "info")
        return {"status": "stopped", "cycles": self._cycle, "stats": self._stats}

    def _main_loop(self):
        """主循环: 每30秒一个周期"""
        while self._running:
            self._cycle += 1
            try:
                # 周期1: 内容生产检查(每周期)
                if self._cycle % 10 == 2:  # 错峰执行
                    self._run_content_production()

                # 周期2: 质量审计(每20周期)
                if self._cycle % 20 == 5:
                    self._run_quality_audit()

                # 周期3: Agent进化(每30周期)
                if self._cycle % 30 == 13:
                    self._run_evolution_cycle()

                # 周期4: 安全扫描(每15周期)
                if self._cycle % 15 == 7:
                    self._run_safety_scan()

                # 周期5: 系统健康(每5周期)
                if self._cycle % 5 == 0:
                    self._run_health_check()

                # 周期6: NPU/GPU保持满载(每10周期)
                if self._cycle % 10 == 0:
                    self._keep_hardware_busy()

                # 周期7: 每50周期全量报告
                if self._cycle % 50 == 0:
                    self._generate_full_report()

            except Exception as e:
                self._log_event("error", f"Cycle {self._cycle} error: {str(e)[:200]}", "warning")
                self._stats["errors_recovered"] += 1

            time.sleep(30)

    def _run_content_production(self):
        """驱动内容生产部日循环"""
        try:
            from agents.content_production_ops import handle_content_production_task
            result = handle_content_production_task({"task_name": "全管道"}, self.db, self.client)
            self._stats["content_production_cycles"] += 1
            self._log_event("content_production", str(result)[:200], "info")
        except Exception as e:
            self._log_event("content_production", f"Failed: {str(e)[:100]}", "warning")

    def _run_quality_audit(self):
        """驱动质量保障部审计"""
        try:
            from agents.quality_safety_ops import QualitySafetyOps
            ops = QualitySafetyOps(None, None, {}, {}, self.db, self.client)
            result = ops.quality_audit_cycle()
            self._stats["quality_audit_cycles"] += 1
            self._log_event("quality_audit", str(result)[:200], "info")
        except Exception as e:
            self._log_event("quality_audit", f"Failed: {str(e)[:100]}", "warning")

    def _run_evolution_cycle(self):
        """驱动演进层周循环"""
        try:
            from agents.evolution_ops import EvolutionOps
            ops = EvolutionOps({}, self.db, self.client)
            result = ops.weekly_evolution_cycle()
            self._stats["evolution_cycles"] += 1
            self._log_event("evolution", str(result)[:200], "info")
        except Exception as e:
            self._log_event("evolution", f"Failed: {str(e)[:100]}", "warning")

    def _run_safety_scan(self):
        """驱动安全双门禁扫描"""
        try:
            from agents.quality_safety_ops import QualitySafetyOps
            ops = QualitySafetyOps(None, None, {}, {}, self.db, self.client)
            result = ops.safety_gate_inbound("system_scan")
            self._stats["safety_checks"] += 1
            self._log_event("safety", str(result)[:200], "info")
        except Exception as e:
            self._log_event("safety", f"Failed: {str(e)[:100]}", "warning")

    def _run_health_check(self):
        """系统健康检查: DB状态+管道状态+Agent状态"""
        try:
            if self.db:
                conn = self.db.get_connection()
                c = conn.cursor()
                c.execute('SELECT COUNT(*) FROM knowledge_points')
                kp = c.fetchone()[0]
                c.execute('SELECT COUNT(*) FROM kp_relations')
                rel = c.fetchone()[0]
                conn.close()
                self._log_event("health", f"KP:{kp} Relations:{rel} Cycle:{self._cycle}", "info")
        except Exception:
            pass

    def _keep_hardware_busy(self):
        """保持NPU/GPU满载: 对大知识库做批量语义搜索和质量分类"""
        try:
            from scripts.npu_engine import NPUEngine
            engine = NPUEngine()
            if self.db:
                conn = self.db.get_connection()
                c = conn.cursor()
                c.execute("SELECT title, original_excerpt FROM knowledge_points WHERE review_status='confirmed' LIMIT 2000")
                rows = c.fetchall()
                conn.close()
                if rows:
                    titles = [r[0] or "" for r in rows]
                    excerpts = [r[1] or "" for r in rows]
                    engine.build_index(titles)
                    engine.quality_classify_batch(titles, excerpts)
                    engine.benchmark(500, 5)
        except Exception:
            pass

    def _generate_full_report(self):
        """全量系统报告"""
        now = datetime.now().isoformat()
        elapsed = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
        report = {
            "time": now,
            "elapsed_hours": round(elapsed / 3600, 1),
            "cycles": self._cycle,
            "stats": self._stats,
            "recent_log": self._log[-10:],
        }
        self._log_event("report", json.dumps(report, ensure_ascii=False)[:500], "info")

    def _log_event(self, event_type, message, severity="info"):
        entry = {
            "time": datetime.now().isoformat(),
            "type": event_type,
            "severity": severity,
            "message": message[:300],
        }
        self._log.append(entry)
        if len(self._log) > 1000:
            self._log = self._log[-500:]

    def get_status(self):
        """获取总控状态"""
        elapsed = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
        return {
            "running": self._running,
            "cycles": self._cycle,
            "elapsed_hours": round(elapsed / 3600, 1),
            "stats": self._stats,
        }
