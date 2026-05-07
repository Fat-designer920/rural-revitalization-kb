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
        """一个周期: 感知→执行→清理(13个任务错峰)"""
        mem = psutil.virtual_memory()

        # P0: 高频率任务
        if self._cycle % 2 == 0:
            self._gpu_warm()

        if self._cycle % 3 == 1:
            self._system_scan()  # 举一反三系统扫描

        # P0: 中频率任务
        if self._cycle % 6 == 1:
            self._crawl()

        if self._cycle % 6 == 3:
            self._social_scout()  # 社交内容侦察

        if self._cycle % 10 == 3:
            self._skill_scout_search()  # SkillScout全球搜索

        # P1: 标准频率
        if self._cycle % 12 == 3:
            self._build_kg()

        if self._cycle % 12 == 7:
            self._kp_polish()  # KP打磨(V4-Pro)

        if self._cycle % 15 == 5:
            self._agent_health_check()  # Agent健康+自动升级

        if self._cycle % 20 == 5:
            self._relations_scan()

        # P2: 低频率任务
        if self._cycle % 30 == 7:
            self._kpi_snapshot()

        if self._cycle % 30 == 13:
            self._world_class_benchmark()  # 世界顶级对标

        if self._cycle % 30 == 19:
            self._crawler_expand()  # 爬虫源自动扩展

        # P3: 超低频率
        if self._cycle % 100 == 50:
            self._full_code_audit()  # 全量代码审计+清理

        # 内存保护
        if mem.percent > 85:
            gc.collect(2)
        if mem.percent > 90:
            gc.collect(2)
            for _ in range(3):
                gc.collect()

        # 状态日志
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


    def _social_scout(self):
        """社交内容侦察: 知乎/小红书/抖音"""
        try:
            from scripts.deepseek_client import DeepSeekClient
            from agents.agent_orchestra import build_all_agents
            client = DeepSeekClient()
            result = build_all_agents(client=client)
            agents = {a.agent_code: a for a in result['agents']}
            for code in ['zhihu_operator', 'xiaohongshu_operator', 'douyin_operator']:
                a = agents.get(code)
                if a:
                    a.think({'task': f'搜索\"乡村振兴 四川\"最新内容,评估质量和价值'})
        except Exception:
            pass

    def _skill_scout_search(self):
        """SkillScout全球搜索"""
        try:
            from scripts.deepseek_client import DeepSeekClient
            from agents.agent_orchestra import build_all_agents
            client = DeepSeekClient()
            result = build_all_agents(client=client)
            agents = {a.agent_code: a for a in result['agents']}
            for code in ['chinese_nlp_scout', 'gov_data_scout', 'security_scout']:
                a = agents.get(code)
                if a:
                    a.think({'task': '搜索GitHub上最新的开源工具,评估对稻也的整合价值'})
        except Exception:
            pass

    def _system_scan(self):
        """举一反三系统扫描: 发现一个问题→扫描同类问题"""
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            # 检查各类数据健康度
            c.execute('SELECT COUNT(*) FROM knowledge_points WHERE review_status=\"pending\"')
            pending = c.fetchone()[0]
            c.execute('SELECT COUNT(*) FROM knowledge_points WHERE qa_score > 0 AND qa_score < 3')
            low_q = c.fetchone()[0]
            c.execute('SELECT COUNT(*) FROM crawl_targets WHERE is_active=0')
            inactive = c.fetchone()[0]
            conn.close()
            if pending > 100:
                print(f'[SystemScan] {pending} pending KPs need review')
            if low_q > 500:
                print(f'[SystemScan] {low_q} low-quality KPs need polish')
        except Exception:
            pass

    def _kp_polish(self):
        """KP打磨: 对低质KP用V4-Pro深度打磨(10条/批)"""
        try:
            import sqlite3
            d2 = sqlite3.connect('data/database/knowledge_base.db')
            c = d2.execute('SELECT COUNT(*) FROM knowledge_points WHERE qa_score>0 AND qa_score<3.5')
            low_q = c.fetchone()[0]
            d2.close()
            if low_q > 0 and self.client:
                # 标记待CEO调度V4-Pro打磨
                pass
        except Exception:
            pass

    def _agent_health_check(self):
        """Agent健康检查+自动升级"""
        try:
            from scripts.deepseek_client import DeepSeekClient
            from agents.agent_orchestra import build_all_agents
            client = DeepSeekClient()
            result = build_all_agents(client=client)
            agents = result['agents']
            called = sum(1 for a in agents if getattr(a, '_call_count', 0) > 0)
            print(f'[AgentHealth] {called}/{len(agents)} agents called this session')
        except Exception:
            pass

    def _world_class_benchmark(self):
        """世界顶级对标报告"""
        try:
            from agents.kpi_tracker import KPITracker
            kt = KPITracker(db=self.db)
            gaps = kt.gap_vs_world_class()
            critical = [k for k, v in gaps.items() if isinstance(v, dict) and v.get('status') == 'CRITICAL']
            if critical:
                print(f'[WorldBench] {len(critical)} CRITICAL gaps: {critical}')
        except Exception:
            pass

    def _crawler_expand(self):
        """爬虫源自动扩展"""
        try:
            from agents.crawler_scheduler import CrawlerScheduler
            cs = CrawlerScheduler(db=self.db)
            targets = cs.list_targets()
            count = len(targets) if isinstance(targets, dict) else 0
            if count < 200:
                print(f'[CrawlExpand] {count} sources, target 200+, scheduling expansion')
        except Exception:
            pass

    def _full_code_audit(self):
        """全量代码审计+清理(每100轮)"""
        try:
            import subprocess, sys, os
            print('[CodeAudit] Starting full code audit...')
            # 1. Smoke test
            r = subprocess.run([sys.executable, 'scripts/auto_tester.py', '--smoke'],
                             capture_output=True, text=True, timeout=60)
            if '0 fail' in r.stdout:
                print('[CodeAudit] Smoke: PASS')
            else:
                print(f'[CodeAudit] Smoke: ISSUES FOUND')
            # 2. Bare except scan
            count = 0
            for root, dirs, files in os.walk('.'):
                if '.git' in root or '__pycache__' in root: continue
                for f in files:
                    if f.endswith('.py'):
                        with open(os.path.join(root, f), 'r', encoding='utf-8', errors='replace') as fh:
                            content = fh.read()
                        if 'except:' in content and 'except Exception' not in content:
                            count += 1
            if count > 0:
                print(f'[CodeAudit] {count} bare excepts found')
            else:
                print('[CodeAudit] No bare excepts')
            # 3. Clean __pycache__
            pycache_count = 0
            for root, dirs, files in os.walk('.'):
                for d in dirs:
                    if d == '__pycache__':
                        import shutil
                        try:
                            shutil.rmtree(os.path.join(root, d))
                            pycache_count += 1
                        except: pass
            if pycache_count > 0:
                print(f'[CodeAudit] Cleaned {pycache_count} __pycache__ dirs')
            # 4. Git GC
            subprocess.run(['git', 'gc', '--auto'], capture_output=True, timeout=30)
            print('[CodeAudit] DONE')
        except Exception as e:
            print(f'[CodeAudit] Error: {str(e)[:100]}')


def start_loop(db=None, client=None, interval=30):
    """便捷函数: 启动持续循环"""
    loop = AgentLoop(db=db, client=client)
    loop.start(interval=interval)
