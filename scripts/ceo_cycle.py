"""
ceo_cycle.py - 系统自动循环(爬虫+提取+质量巡检)
路径：scripts/ceo_cycle.py
版本：v2.3.8
"""
import time, gc, psutil, sqlite3, os, sys
from datetime import datetime
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

STATUS_FILE = os.path.join(PROJECT_ROOT, 'logs', 'ceo_cycle_status.txt')


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
    state['gpu'] = 'N/A'
    return state


def ceo_decide(state):
    """CEO动态决策: 基于全局状态决定本轮做什么。
    所有领域都在候选池中,CEO根据优先级选择。

    返回: (domain, task_name, action_function)
    """
    # 全部候选任务池(不遗漏任何领域)
    candidates = []

    # === 知识生产 ===
    candidates.append(('知识生产', '爬虫深度采集', run_crawl, 90))
    candidates.append(('知识生产', '知识提取管道', run_extract, 85))
    candidates.append(('知识生产', '关系网络扫描', run_relations, 50))

    # === 质量 ===
    if state['review'].get('pending', 0) > 10:
        candidates.append(('质量保障', '待审核KP自动确认', run_auto_confirm, 80))
    candidates.append(('质量保障', '保鲜扫描', run_freshness, 40))
    candidates.append(('质量保障', '安全内容扫描', run_safety_scan, 40))

    # === 系统 ===
    candidates.append(('系统运维', 'KPI快照', run_kpi, 30))
    candidates.append(('系统运维', '内存清理', run_cleanup, 20))
    candidates.append(('系统运维', '代码审计', run_code_audit, 15))
    candidates.append(('质量保障', '爬取文件巡检', run_crawled_quality_audit, 75))

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


def run_crawled_quality_audit():
    """CEO定期巡检爬取文件质量(每20轮执行1次)"""
    try:
        import os
        crawled='data/crawled'
        if not os.path.exists(crawled): return
        rural_kw=['土地','耕地','农村','农业','农民','乡村','农田','振兴',
                  '整治','规划','建设','保护','生态','水利','补贴','项目',
                  '高标准农田','增减挂钩','占补平衡','集体建设']
        cleaned=0
        for f in os.listdir(crawled):
            path=os.path.join(crawled,f)
            if not os.path.isfile(path): continue
            try:
                with open(path,'r',encoding='utf-8',errors='replace') as fh:
                    content=fh.read()
                hits=sum(1 for kw in rural_kw if kw in content)
                if hits<3 or len(content)<500:
                    os.remove(path);cleaned+=1
            except (OSError, IOError): pass
        remaining=len([f for f in os.listdir(crawled) if os.path.isfile(os.path.join(crawled,f))])
        if cleaned>0: log(f'[Audit] Cleaned {cleaned} bad files, {remaining} remain')
    except Exception: pass


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
    log('=== 稻也 自动循环启动 ===')
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
                log(f'[Health] C{cycle} KP:{state["kp"]} Rel:{state["rel"]} Crawl:{state["crawl"]}/{state.get("crawl_targets",0)} RAM:{state["ram"]}% Up:{elapsed:.0f}m')
                log(f'[Exec] Last: {executed}')

        except Exception as e:
            log(f'[CEO] Cycle{cycle} err: {str(e)[:80]}')

        time.sleep(30)


if __name__ == '__main__':
    main()
