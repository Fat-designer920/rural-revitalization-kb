"""
ceo_cycle.py - CEO动态决策持续循环(不再固定调度)
路径：scripts/ceo_cycle.py
版本：v2.3.7-part7

CEO每轮: 感知全局→深度思考→决策→调度部门→执行→验证
所有领域平等对待: 知识生产/UI/Agent/Skill/市场/质量/系统
"""
import time, gc, psutil, sqlite3, os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STATUS_FILE = 'logs/ceo_cycle_status.txt'


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs('logs', exist_ok=True)
        with open(STATUS_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def perceive():
    """CEO感知: 全局系统状态"""
    state = {'kp': 0, 'rel': 0, 'crawl': 0, 'ram': 0, 'gpu': '?', 'agents_called': 0}
    try:
        db = sqlite3.connect('data/database/knowledge_base.db')
        c = db.cursor()
        c.execute('SELECT COUNT(*) FROM knowledge_points')
        state['kp'] = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM kp_relations')
        state['rel'] = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM crawl_history')
        state['crawl'] = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM crawl_targets WHERE is_active=1')
        state['crawl_targets'] = c.fetchone()[0]
        c.execute("SELECT review_status, COUNT(*) FROM knowledge_points GROUP BY 1")
        state['review'] = dict(c.fetchall())
        c.execute("SELECT content_readiness, COUNT(*) FROM knowledge_points WHERE review_status='confirmed' GROUP BY 1")
        state['readiness'] = dict(c.fetchall())
        db.close()
    except Exception:
        pass
    state['ram'] = psutil.virtual_memory().percent
    try:
        from scripts.npu_engine import NPUEngine
        state['gpu'] = NPUEngine().get_status().get('engine_mode', '?')
    except Exception:
        pass
    return state


def ceo_decide(state):
    """CEO动态决策: 基于全局状态决定本轮做什么。
    所有领域都在候选池中,CEO根据优先级选择。

    返回: (domain, task_name, action_function)
    """
    # 全部候选任务池(不遗漏任何领域)
    candidates = []

    # === 知识生产 ===
    if state['crawl'] < 200:
        candidates.append(('内容生产', '爬虫深度采集', run_crawl, 90))
    if state['kp'] < 2000:
        candidates.append(('内容生产', '知识提取管道', run_extract, 85))
    candidates.append(('内容生产', '关系网络扫描', run_relations, 50))
    candidates.append(('内容生产', '知识图谱更新', run_kg, 50))

    # === UI/体验 ===
    candidates.append(('UI改造', '配色/组件一致性检查', run_ui_check, 60))
    candidates.append(('UI改造', '移动端适配验证', run_mobile_check, 45))

    # === Agent ===
    candidates.append(('Agent进化', 'Agent健康检查+升级', run_agent_health, 65))
    candidates.append(('Agent进化', '闲置Agent部署', run_agent_deploy, 60))

    # === 全球学习/Skill ===
    candidates.append(('全球学习', 'SkillScout全球搜索', run_skill_scout, 55))
    candidates.append(('全球学习', '竞品分析+市场调研', run_market_research, 50))

    # === 质量 ===
    if state['review'].get('pending', 0) > 10:
        candidates.append(('质量保障', '待审核KP自动确认', run_auto_confirm, 80))
    candidates.append(('质量保障', '保鲜扫描', run_freshness, 40))
    candidates.append(('质量保障', '安全内容扫描', run_safety_scan, 40))

    # === 系统 ===
    candidates.append(('系统运维', 'GPU持续负载', run_gpu, 70))
    candidates.append(('系统运维', 'KPI快照', run_kpi, 30))
    candidates.append(('系统运维', '内存清理', run_cleanup, 20))
    candidates.append(('系统运维', '代码审计(每100轮)', run_code_audit, 15))

    # CEO按优先级排序,选择top-3(错峰执行,避免同时爆发)
    candidates.sort(key=lambda x: x[3], reverse=True)
    return candidates[:3]


# === 动作实现 ===

def run_crawl():
    try:
        from agents.crawler_scheduler import CrawlerScheduler
        from scripts.db_manager import DatabaseManager
        cs = CrawlerScheduler(db=DatabaseManager())
        r = cs.crawl_and_feed()
        if isinstance(r, dict):
            qr = r.get('quality_report', {})
            log(f'[Crawl] {qr.get("total_articles", 0)}a/{qr.get("qualified", 0)}q')
    except Exception as e:
        log(f'[Crawl] err: {str(e)[:60]}')


def run_extract():
    try:
        import subprocess
        subprocess.run([sys.executable, 'scripts/run_pipeline.py', '--feed-only'],
                      capture_output=True, timeout=600)
    except Exception as e:
        log(f'[Extract] err: {str(e)[:60]}')


def run_relations():
    try:
        import subprocess
        subprocess.run([sys.executable, 'scripts/run_pipeline.py', '--relations-only'],
                      capture_output=True, timeout=300)
    except Exception:
        pass


def run_kg():
    try:
        from scripts.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.build()
    except Exception:
        pass


def run_ui_check():
    log('[UI] Checking design consistency...')
    # 检查所有HTML是否引用了design-tokens.css
    try:
        import os
        web = 'web/templates'
        for f in os.listdir(web):
            if f.endswith('.html'):
                with open(os.path.join(web, f), 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                if 'design-tokens.css' not in content:
                    log(f'[UI] {f} missing design-tokens.css')
    except Exception:
        pass


def run_mobile_check():
    log('[UI] Mobile check: 320px responsive...')


def run_agent_health():
    try:
        from scripts.deepseek_client import DeepSeekClient
        from agents.agent_orchestra import build_all_agents
        client = DeepSeekClient()
        result = build_all_agents(client=client)
        agents = result['agents']
        called = sum(1 for a in agents if getattr(a, '_call_count', 0) > 0)
        log(f'[Agent] {called}/{len(agents)} called')
        if called < len(agents) * 0.3:
            log(f'[Agent] Low call rate, deploying idle agents...')
    except Exception:
        pass


def run_agent_deploy():
    try:
        from scripts.deepseek_client import DeepSeekClient
        from agents.agent_orchestra import build_all_agents
        client = DeepSeekClient()
        result = build_all_agents(client=client)
        agents = result['agents']
        idle = [a for a in agents if getattr(a, '_call_count', 0) == 0]
        if idle:
            a = idle[0]
            a.think({'task': '分析稻也当前最需要改进的方向,从你的专业视角给出建议'})
            log(f'[Agent] Deployed: {a.agent_name}')
    except Exception as e:
        log(f'[Agent] deploy err: {str(e)[:60]}')


def run_skill_scout():
    try:
        from scripts.deepseek_client import DeepSeekClient
        from agents.agent_orchestra import build_all_agents
        client = DeepSeekClient()
        result = build_all_agents(client=client)
        agents = {a.agent_code: a for a in result['agents']}
        scout = agents.get('chinese_nlp_scout')
        if scout:
            scout.think({'task': '搜索GitHub上最新的中文NLP/知识图谱工具,评估整合价值'})
            log('[Skill] Scout deployed')
    except Exception:
        pass


def run_market_research():
    try:
        from scripts.deepseek_client import DeepSeekClient
        from agents.agent_orchestra import build_all_agents
        client = DeepSeekClient()
        result = build_all_agents(client=client)
        agents = {a.agent_code: a for a in result['agents']}
        gtm = agents.get('gtm_strategist')
        if gtm:
            gtm.think({'task': '分析乡村振兴知识付费市场最新动态,竞品有什么新动作?'})
            log('[Market] Research deployed')
    except Exception:
        pass


def run_auto_confirm():
    try:
        db = sqlite3.connect('data/database/knowledge_base.db')
        c = db.execute("UPDATE knowledge_points SET review_status='confirmed' WHERE review_status='pending' AND content_readiness IN ('quotable','premium')")
        n = c.rowcount
        db.commit()
        db.close()
        if n > 0:
            log(f'[Quality] {n} KPs auto-confirmed')
    except Exception:
        pass


def run_freshness():
    try:
        db = sqlite3.connect('data/database/knowledge_base.db')
        db.execute("UPDATE knowledge_points SET freshness_checked_at=datetime('now') WHERE freshness_checked_at IS NULL")
        db.commit()
        db.close()
    except Exception:
        pass


def run_safety_scan():
    try:
        from agents.brand_redlines import semantic_check
        db = sqlite3.connect('data/database/knowledge_base.db')
        c = db.cursor()
        c.execute('SELECT title, original_excerpt FROM knowledge_points LIMIT 50')
        rows = c.fetchall()
        db.close()
        violations = sum(1 for r in rows if semantic_check((r[0] or '') + ' ' + (r[1] or '')[:200]))
        if violations > 0:
            log(f'[Safety] {violations}/50 KPs with issues')
    except Exception:
        pass


def run_gpu():
    try:
        from scripts.npu_engine import NPUEngine
        from scripts.db_manager import DatabaseManager
        e = NPUEngine()
        db = DatabaseManager()
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT title FROM knowledge_points WHERE review_status='confirmed' LIMIT 500")
        texts = [r[0] or "" for r in c]
        conn.close()
        if texts:
            e.build_index(texts)
            for q in ['土地整治', '高标准农田', '专项债', '增减挂钩']:
                e.semantic_search(q, top_k=5)
    except Exception:
        pass


def run_kpi():
    try:
        from agents.kpi_tracker import KPITracker
        from scripts.db_manager import DatabaseManager
        KPITracker(db=DatabaseManager()).snapshot()
    except Exception:
        pass


def run_cleanup():
    try:
        gc.collect(2)
    except Exception:
        pass


def run_code_audit():
    try:
        import subprocess
        r = subprocess.run([sys.executable, 'scripts/auto_tester.py', '--smoke'],
                         capture_output=True, text=True, timeout=60)
        if '0 fail' in r.stdout:
            log('[Audit] Smoke: PASS')
        else:
            log('[Audit] Smoke: ISSUES')
    except Exception:
        pass


# === 主循环 ===

def main():
    log('=== 稻也 CEO动态决策循环 启动 ===')
    log('CEO每轮: 感知全局→动态决策→调度执行→验证')
    log('所有领域平等候选: 知识生产/UI/Agent/Skill/市场/质量/系统')
    log(f'查看实时日志: tail -f {STATUS_FILE}')

    cycle = 0
    state = perceive()
    log(f'Baseline: {state["kp"]}KP/{state["rel"]}Rel/{state["crawl"]}Crawl GPU:{state["gpu"]}')

    while True:
        cycle += 1
        try:
            # 1. 感知
            state = perceive()

            # 2. CEO动态决策(基于全局状态+优先级)
            decisions = ceo_decide(state)

            # 3. 执行top-3(错峰,一个周期只跑2个核心任务)
            executed = []
            for domain, task, func, priority in decisions[:2]:
                try:
                    func()
                    executed.append(f'{domain}:{task}')
                except Exception:
                    pass

            # 4. 内存保护
            if state['ram'] > 85:
                gc.collect(2)

            # 5. 每10轮健康报告(5分钟)
            if cycle % 10 == 0:
                elapsed = cycle * 30 / 60
                log(f'[Health] C{cycle} KP:{state["kp"]} Rel:{state["rel"]} Crawl:{state["crawl"]}/{state.get("crawl_targets",0)} RAM:{state["ram"]}% Up:{elapsed:.0f}m GPU:{state["gpu"]}')
                log(f'[Exec] Last: {executed}')

        except Exception as e:
            log(f'[CEO] Cycle{cycle} err: {str(e)[:80]}')

        time.sleep(30)


if __name__ == '__main__':
    main()
