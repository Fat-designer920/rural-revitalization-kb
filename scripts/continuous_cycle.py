"""
continuous_cycle.py - 持续循环引擎(todos驱动,workspace可见)
路径：scripts/continuous_cycle.py
版本：v2.3.7-part7

每30秒一轮,每轮输出到logs/cycle_status.txt(工作区可见)
失败不中断,完成自动生成下批任务
"""
import time, gc, psutil, sqlite3, os, sys
from datetime import datetime
# 确保项目根在path中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CYCLE_LOG = 'logs/cycle_status.txt'
BATCH_INTERVAL = 30  # 每批30秒


def log(msg):
    """写入状态文件(工作区可见)"""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs('logs', exist_ok=True)
        with open(CYCLE_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def check_db():
    """检查数据库核心指标"""
    try:
        db = sqlite3.connect('data/database/knowledge_base.db')
        c = db.cursor()
        c.execute('SELECT COUNT(*) FROM knowledge_points')
        kp = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM kp_relations')
        rel = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM crawl_history')
        ch = c.fetchone()[0]
        db.close()
        return kp, rel, ch
    except Exception:
        return 0, 0, 0


def run_crawl():
    """爬虫任务"""
    try:
        from agents.crawler_scheduler import CrawlerScheduler
        from scripts.db_manager import DatabaseManager
        cs = CrawlerScheduler(db=DatabaseManager())
        r = cs.crawl_and_feed()
        if isinstance(r, dict):
            qr = r.get('quality_report', {})
            articles = qr.get('total_articles', 0)
            qualified = qr.get('qualified', 0)
            if articles > 0:
                log(f'[Crawl] {articles} articles, {qualified} qualified')
    except Exception as e:
        log(f'[Crawl] err: {str(e)[:60]}')


def run_gpu():
    """GPU负荷"""
    try:
        from scripts.npu_engine import NPUEngine
        from scripts.db_manager import DatabaseManager
        e = NPUEngine()
        db = DatabaseManager()
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT title,original_excerpt FROM knowledge_points WHERE review_status='confirmed' LIMIT 500")
        rows = [(r[0] or "") + " " + (r[1] or "")[:100] for r in c]
        conn.close()
        if rows:
            e.build_index(rows)
            for q in ['土地整治', '高标准农田', '专项债', '增减挂钩']:
                e.semantic_search(q, top_k=5)
    except Exception as e:
        pass


def run_pipeline():
    """全管道"""
    try:
        import subprocess
        subprocess.run([sys.executable, 'scripts/run_pipeline.py', '--crawl'],
                      capture_output=True, timeout=300)
    except Exception:
        pass


def main():
    log('=== 稻也持续循环启动(todos驱动,workspace可见) ===')
    kp_base, _, _ = check_db()
    log(f'Baseline: {kp_base} KP')

    cycle = 0
    while True:
        cycle += 1
        try:
            # 检查内存
            mem = psutil.virtual_memory()
            if mem.percent > 85:
                gc.collect(2)

            # 错峰执行任务
            if cycle % 2 == 0:
                run_gpu()

            if cycle % 8 == 1:
                run_crawl()

            if cycle % 15 == 3:
                run_pipeline()

            # 每5轮健康报告(2.5分钟)
            if cycle % 5 == 0:
                kp, rel, ch = check_db()
                elapsed = cycle * BATCH_INTERVAL / 60
                log(f'[Health] Cycle{cycle} KP:{kp} Rel:{rel} Crawl:{ch} RAM:{mem.percent}% Up:{elapsed:.0f}m')
                if kp > kp_base:
                    log(f'[GROWTH] +{kp - kp_base} new KPs!')

        except Exception as e:
            log(f'[Error] Cycle{cycle}: {str(e)[:80]}')

        time.sleep(BATCH_INTERVAL)


if __name__ == '__main__':
    main()
