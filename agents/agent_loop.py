"""
agent_loop.py - 持续自主循环(学习OpenClaw/Nanobot的AgentLoop模式)
路径：agents/agent_loop.py
版本：v2.3.7-part7

核心: while True循环,单进程内持续运行,不依赖subprocess。"""
import time, gc, psutil, sqlite3, traceback, os, sys
from datetime import datetime


class AgentLoop(object):
    """持续自主循环 — 学习OpenClaw的AgentLoop模式。
    单进程while True,每个周期: 感知→决策→执行→学习→休眠。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client
        self._running = False
        self._cycle = 0
        self._start_time = None
        self._errors = 0
        self._max_errors = 10

    def start(self, interval=30):
        """启动持续循环。interval=周期间隔(秒)。"""
        self._running = True
        self._start_time = datetime.now()
        self._cycle = 0
        self._errors = 0
        print(f'[AgentLoop] Started at {self._start_time.strftime("%H:%M:%S")}, interval={interval}s')
        try:
            self._main_loop(interval)
        except KeyboardInterrupt:
            print(f'[AgentLoop] Stopped by user')
        except Exception as e:
            print(f'[AgentLoop] Fatal: {e}')
        finally:
            self._running = False

    def stop(self):
        self._running = False

    def _main_loop(self, interval):
        while self._running:
            self._cycle += 1
            cycle_start = time.time()
            try:
                self._run_cycle()
                self._errors = 0  # 成功后重置错误计数
            except Exception as e:
                self._errors += 1
                print(f'[Cycle{self._cycle}] Error ({self._errors}/{self._max_errors}): {str(e)[:100]}')
                if self._errors >= self._max_errors:
                    print(f'[AgentLoop] Too many errors, stopping')
                    self._running = False
                    break
                traceback.print_exc()

            # 休眠到下一个周期
            elapsed = time.time() - cycle_start
            sleep_time = max(1, interval - elapsed)
            time.sleep(sleep_time)

    def _run_cycle(self):
        """一个周期: 感知→执行→清理"""
        # 1. 感知: 检查系统状态
        mem = psutil.virtual_memory()

        # 2. 执行: 根据周期号触发不同任务(错峰执行)
        if self._cycle % 2 == 0:
            self._gpu_warm()

        if self._cycle % 6 == 1:
            self._crawl()

        if self._cycle % 12 == 3:
            self._build_kg()

        if self._cycle % 20 == 5:
            self._relations_scan()

        if self._cycle % 30 == 7:
            self._kpi_snapshot()

        # 3. 内存保护
        if mem.percent > 85:
            gc.collect(2)
        if mem.percent > 90:
            # 紧急: 强制释放
            gc.collect(2)

        # 4. 状态日志(每10轮)
        if self._cycle % 10 == 0:
            self._health_check()

    def _gpu_warm(self):
        """GPU保持活跃: 批量语义搜索"""
        try:
            from scripts.npu_engine import NPUEngine
            e = NPUEngine()
            conn = self.db.get_connection() if self.db else None
            if conn:
                c = conn.cursor()
                c.execute("SELECT title FROM knowledge_points WHERE review_status='confirmed' LIMIT 300")
                texts = [r[0] or "" for r in c]
                conn.close()
                if texts:
                    e.build_index(texts)
                    for _ in range(10):
                        e.semantic_search("土地整治", top_k=5)
        except Exception:
            pass

    def _crawl(self):
        """爬虫采集"""
        try:
            from agents.crawler_scheduler import CrawlerScheduler
            cs = CrawlerScheduler(db=self.db)
            cs.run_scheduled()
        except Exception:
            pass

    def _build_kg(self):
        """知识图谱更新"""
        try:
            from scripts.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph()
            kg.build()
        except Exception:
            pass

    def _relations_scan(self):
        """关系扫描"""
        try:
            import subprocess, sys
            subprocess.run([sys.executable, 'scripts/run_pipeline.py', '--relations-only'],
                          capture_output=True, timeout=300)
        except Exception:
            pass

    def _kpi_snapshot(self):
        """KPI快照"""
        try:
            from agents.kpi_tracker import KPITracker
            kt = KPITracker(db=self.db)
            kt.snapshot()
        except Exception:
            pass

    def _health_check(self):
        """健康检查"""
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM knowledge_points')
            kp = c.fetchone()[0]
            c.execute('SELECT COUNT(*) FROM kp_relations')
            rel = c.fetchone()[0]
            conn.close()
            mem = psutil.virtual_memory()
            elapsed = (datetime.now() - self._start_time).total_seconds() / 3600
            print(f'[{datetime.now().strftime("%H:%M:%S")}] '
                  f'Cycle{self._cycle} KP:{kp} Rel:{rel} '
                  f'RAM:{mem.percent}% Up:{elapsed:.1f}h')
        except Exception:
            pass


def start_loop(db=None, client=None, interval=30):
    """便捷函数: 启动持续循环"""
    loop = AgentLoop(db=db, client=client)
    loop.start(interval=interval)
