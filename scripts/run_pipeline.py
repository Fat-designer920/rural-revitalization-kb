"""
run_pipeline.py - 知识管道CLI入口(喂料→提取→质检→关系→精品)
路径：scripts/run_pipeline.py
版本：v2.3.7-part2
用法:
  python scripts/run_pipeline.py --full              # 全管道
  python scripts/run_pipeline.py --feed-only         # 仅喂料+提取
  python scripts/run_pipeline.py --qc-only           # 仅质检补跑
  python scripts/run_pipeline.py --relations-only    # 仅关系扫描
  python scripts/run_pipeline.py --premium-only      # 仅精品判定
  python scripts/run_pipeline.py --status            # 查看当前状态
  python scripts/run_pipeline.py --dry-run           # 预览会处理多少文件
"""
import sys, os, time, json
from pathlib import Path

# v2.3.7-part3: Windows GBK控制台UTF-8适配
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT))


def get_db():
    from db_manager import DatabaseManager
    db = DatabaseManager()
    db.init_tables()
    return db


def get_client():
    from deepseek_client import DeepSeekClient
    config_path = PROJECT_ROOT / "config" / "settings.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return DeepSeekClient(config)


def print_status(db):
    """打印知识库当前状态"""
    conn = db.get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM knowledge_points")
    total = c.fetchone()[0]
    c.execute("SELECT review_status, COUNT(*) FROM knowledge_points GROUP BY review_status")
    rs = dict(c.fetchall())
    c.execute("SELECT content_readiness, COUNT(*) FROM knowledge_points GROUP BY content_readiness")
    cr = dict(c.fetchall())
    c.execute("SELECT COUNT(*) FROM source_files")
    sfs = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT source_file_id) FROM knowledge_points")
    sf_kp = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM kp_relations")
    rels = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM consensus_clusters")
    clus = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM annotations")
    anns = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM qa_history")
    qas = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score IS NULL OR qa_score = 0.0")
    need_qc = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM crawl_history")
    crawls = c.fetchone()[0]
    conn.close()

    print("=" * 60)
    print("  知识库状态")
    print("=" * 60)
    print(f"  知识点总数:        {total:>6}")
    print(f"    pending(待审):    {rs.get('pending', 0):>6}")
    print(f"    confirmed(已审):  {rs.get('confirmed', 0):>6}")
    print(f"    draft(草稿):      {cr.get('draft', 0):>6}")
    print(f"    quotable(可引用):  {cr.get('quotable', 0):>6}")
    print(f"    premium(精品):    {cr.get('premium', 0):>6}")
    print(f"  源文件:             {sfs:>6} (有KP的: {sf_kp})")
    print(f"  知识关系边:         {rels:>6}")
    print(f"  共识簇:             {clus:>6}")
    print(f"  专家注解:           {anns:>6}")
    print(f"  问答历史:           {qas:>6}")
    print(f"  待质检:             {need_qc:>6}")
    print(f"  爬虫抓取:           {crawls:>6}")
    print("=" * 60)


def print_dry_run():
    """预览待处理文件"""
    db = get_db()
    from agents.auto_feeder import AutoFeeder
    feeder = AutoFeeder(db=db)
    inv = feeder.inventory_test_files()
    already = feeder.get_already_processed()
    pending = [f for f in inv if f["name"] not in already]
    print(f"测试文件总数: {len(inv)}")
    print(f"已处理: {len(inv) - len(pending)}")
    print(f"待处理: {len(pending)}")
    if pending:
        print("\n待处理文件列表:")
        for i, f in enumerate(pending, 1):
            print(f"  {i:>3}. [{f['subdir']}] {f['name']} ({f['size']//1024}KB)")


def run_full(db, client):
    """全管道运行"""
    from agents.auto_feeder import AutoFeeder

    def progress(data):
        stage = data.get("stage", "?")
        cur = data.get("current", 0)
        tot = data.get("total", 0)
        msg = data.get("message", "")
        bar = "#" * max(1, int(20 * cur / max(1, tot)))
        print(f"\r  [{stage}] [{bar:<20}] {cur}/{tot}  {msg}", end="", flush=True)
        if stage in ("pipeline_done", "batch_done"):
            print()

    feeder = AutoFeeder(db=db, client=client, progress_callback=progress)
    report = feeder.run_full_pipeline(model_key="parallel", run_relations=True)
    print("\n")
    print("=" * 60)
    print("  管道运行报告")
    print("=" * 60)
    stages = report.get("stages", {})
    for name, result in stages.items():
        if isinstance(result, dict):
            status = "OK" if result.get("success", True) else "FAIL"
            if "total_kps" in result:
                print(f"  [{name}] {status}: +{result['total_kps']}KPs, "
                      f"耗时{result.get('elapsed_sec','?')}秒, "
                      f"估算¥{result.get('cost_estimate_cny','?')}")
            elif "processed" in result:
                print(f"  [{name}] {status}: {result['processed']}条处理")
            elif "relations_found" in result:
                print(f"  [{name}] {status}: {result['relations_found']}组关系")
            elif "promoted_to_quotable" in result:
                print(f"  [{name}] {status}: {result['promoted_to_quotable']}条升级")
            elif "skipped" in result:
                print(f"  [{name}] 跳过")
        elif name == "summary":
            print(f"  [{name}] 总KP:{result.get('total_kps','?')} "
                  f" 已审:{result.get('confirmed_kps','?')} "
                  f" 精品:{result.get('premium_kps','?')} "
                  f" 关系:{result.get('relation_edges','?')}")
    print("=" * 60)
    return report


def run_qc_only(db, client):
    """仅质检补跑"""
    print("质检补跑中...")
    from agents.auto_feeder import AutoFeeder
    feeder = AutoFeeder(db=db, client=client)
    result = feeder._run_full_qc()
    print(f"完成: {result.get('processed', 0)}条KP质检")
    result2 = feeder._run_readiness_promote()
    print(f"就绪度联动: {result2.get('promoted_to_quotable', 0)}条draft→quotable")


def run_relations_only(db, client):
    """仅关系扫描"""
    print("知识关系全量扫描中...")
    from agents.auto_feeder import AutoFeeder
    feeder = AutoFeeder(db=db, client=client)
    result = feeder._run_full_relations()
    print(f"完成: {result.get('relations_found', 0)}组关系")


def run_premium_only(db, client):
    """仅精品判定"""
    print("精品候选判定中(可能耗时较长)...")
    from scripts.premium_judge import run_premium_refresh
    result = run_premium_refresh(db, client, progress_callback=None, cancel_check=None)
    if isinstance(result, dict):
        print(f"完成: {result.get('total_judged', '?')}条判定")


def main():
    if "--status" in sys.argv:
        db = get_db()
        print_status(db)
    elif "--dry-run" in sys.argv:
        print_dry_run()
    elif "--qc-only" in sys.argv:
        db = get_db(); client = get_client()
        run_qc_only(db, client)
    elif "--relations-only" in sys.argv:
        db = get_db(); client = get_client()
        run_relations_only(db, client)
    elif "--premium-only" in sys.argv:
        db = get_db(); client = get_client()
        run_premium_only(db, client)
    elif "--feed-only" in sys.argv:
        db = get_db(); client = get_client()
        from agents.auto_feeder import AutoFeeder
        feeder = AutoFeeder(db=db, client=client)
        result = feeder.feed_all(model_key="parallel")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif "--exp-inbox" in sys.argv:
        db = get_db(); client = get_client()
        from agents.auto_feeder import AutoFeeder
        feeder = AutoFeeder(db=db, client=client)
        result = feeder.watch_experience_inbox()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif "--crawl" in sys.argv:
        db = get_db()
        from agents.crawler_scheduler import CrawlerScheduler
        cs = CrawlerScheduler(db=db)
        result = cs.run_scheduled(schedule='weekly')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif "--crawl-and-feed" in sys.argv:
        db = get_db()
        from agents.crawler_scheduler import CrawlerScheduler
        cs = CrawlerScheduler(db=db)
        result = cs.crawl_and_feed(schedule='weekly')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif "--search" in sys.argv:
        db = get_db(); client = get_client()
        from agents.smart_search_agent import SmartSearchAgent
        from agents.knowledge_gap_analyzer import get_knowledge_needs
        needs = get_knowledge_needs()
        agent = SmartSearchAgent(db=db, client=client)
        result = agent.search_by_knowledge_needs(needs["all_needs"][:10])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif "--retry-failed" in sys.argv:
        db = get_db()
        print("重试失败文件...")
        conn = db.get_connection(); c = conn.cursor()
        c.execute("SELECT id, renamed_filename FROM source_files WHERE process_status='failed'")
        failed = c.fetchall(); conn.close()
        print(f"失败文件: {len(failed)}")
        for f in failed:
            c2 = db.get_connection().cursor()
            c2.execute("UPDATE source_files SET process_status='processing', process_message='自动重试' WHERE id=?", (f[0],))
            db.get_connection().commit(); c2.close()
        print(f"已重置{len(failed)}个文件为processing状态,将自动进入提取队列")
    elif "--verify-sources" in sys.argv:
        db = get_db()
        from agents.source_verifier import SourceVerifier
        sv = SourceVerifier(db=db)
        result = sv.seed_whitelist()
        status = sv.get_whitelist_status()
        print(json.dumps({"seeded": result, "status": status}, ensure_ascii=False, indent=2))
    elif "--full" in sys.argv:
        db = get_db()
        client = get_client()
        run_full(db, client)
    else:
        print(__doc__)
        print("\n常用命令:")
        print("  python scripts/run_pipeline.py --status         查看知识库状态")
        print("  python scripts/run_pipeline.py --dry-run        预览待处理文件")
        print("  python scripts/run_pipeline.py --feed-only      仅喂料+提取")
        print("  python scripts/run_pipeline.py --exp-inbox      扫描经验收件箱")
        print("  python scripts/run_pipeline.py --crawl          执行爬虫(weekly目标)")
        print("  python scripts/run_pipeline.py --crawl-and-feed 爬虫+自动提取")
        print("  python scripts/run_pipeline.py --search         智能搜索(缺口驱动)")
        print("  python scripts/run_pipeline.py --qc-only        质检补跑+就绪度联动")
        print("  python scripts/run_pipeline.py --relations-only 关系全量扫描")
        print("  python scripts/run_pipeline.py --premium-only   精品候选判定")
        print("  python scripts/run_pipeline.py --retry-failed   重试失败文件")
        print("  python scripts/run_pipeline.py --verify-sources 信源白名单状态")
        print("  python scripts/run_pipeline.py --full           一键全管道")


if __name__ == "__main__":
    main()
