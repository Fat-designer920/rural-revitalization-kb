"""
run_pipeline.py - 知识管道CLI入口(深度爬取→喂料→提取→质检→关系→精品)
路径：scripts/run_pipeline.py
版本：v2.3.7-part7
用法:
  python scripts/run_pipeline.py --full              # 全管道
  python scripts/run_pipeline.py --feed-only         # 仅喂料+提取
  python scripts/run_pipeline.py --qc-only           # 仅质检补跑
  python scripts/run_pipeline.py --relations-only    # 仅关系扫描
  python scripts/run_pipeline.py --premium-only      # 仅精品判定
  python scripts/run_pipeline.py --status            # 查看当前状态
  python scripts/run_pipeline.py --dry-run           # 预览会处理多少文件
"""
import sys, json
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
        src = None
        if "--crawl" in sys.argv:
            idx = sys.argv.index("--crawl")
            if idx + 1 < len(sys.argv) and not sys.argv[idx+1].startswith("--"):
                src = [s.strip() for s in sys.argv[idx+1].split(",")]
        print(f"爬取 v2.3.8 (信源: {src or '全部'})...")
        result = cs.run(sources=src)
        stats = result.get("stats", {})
        print(f"\n{'='*60}")
        print(f"  爬取报告 v2.3.8")
        print(f"{'='*60}")
        print(f"  抓取列表页:       {stats.get('pages_fetched', 0):>6}")
        print(f"  发现链接:         {stats.get('links_found', 0):>6}")
        print(f"  提取文章:         {stats.get('articles_fetched', 0):>6}")
        print(f"  合格:             {stats.get('qualified', 0):>6}  <- CEO审核批准后入库")
        print(f"  拒绝:             {stats.get('rejected', 0):>6}")
        print(f"  去重跳过:         {stats.get('duplicates', 0):>6}")
        print(f"  错误:             {stats.get('errors', 0):>6}")
        print(f"{'='*60}")
        print(f"\n  {result.get('message', '')}")
        if result.get("articles"):
            print(f"\n  合格文章:")
            for a in result["articles"]:
                print(f"    [{a.get('source_name','')}] {a['title'][:60]}")
                print(f"      字数:{a.get('char_count',0)} | {a.get('filename','')}")
        if result.get("reject_log"):
            print(f"\n  拒绝详情(前5条):")
            for r in result["reject_log"][:5]:
                print(f"    [{r['quality']}] {r['reason'][:80]}")
        if result.get("report_path"):
            print(f"\n  完整报告: {result['report_path']}")
    elif "--crawl-status" in sys.argv:
        db = get_db()
        from agents.crawler_scheduler import CrawlerScheduler
        from scripts.crawler_extractor import CrawlerExtractor
        cs = CrawlerScheduler(db=db)
        ce = CrawlerExtractor(db=db)
        s = cs.get_status()
        print(f"爬虫状态 v2.3.8 (手动触发模式)")
        print(f"  搜索端点: {s.get('search_endpoints', '?')}个")
        print(f"  关键词组: {s.get('keyword_groups', '?')}组")
        print(f"  历史爬取总数: {s.get('total_crawls', '?')}")
        print(f"  最近运行: {s.get('last_run', '从未')}")
        cstats = ce.get_crawled_stats()
        print(f"  待审核文件: {cstats['total']}个 ({cstats.get('total_size_kb',0)}KB)")
        if cstats.get("files"):
            for f in cstats["files"][:10]:
                print(f"    {f['filename']}")
    elif "--crawl-approve" in sys.argv:
        db = get_db()
        from scripts.crawler_extractor import CrawlerExtractor
        ce = CrawlerExtractor(db=db)
        print("批准爬取文件→移至pending/触发提取管道...")
        result = ce.batch_approve_and_process()
        print(f"\n  {result['message']}")
        for a in result["approved"]:
            print(f"  [OK] {Path(a['to']).name}")
        for e in result["errors"]:
            print(f"  [ERR] {e['file']}: {e['error']}")
        print("\n  下一步: python scripts/run_pipeline.py --feed-only")
    elif "--discover" in sys.argv:
        from agents.source_discoverer import SourceDiscoverer
        sd = SourceDiscoverer()
        # 解析域名参数: --discover 或 --discover www.mianyang.gov.cn,www.luzhou.gov.cn
        domains = None
        idx = sys.argv.index("--discover")
        if idx + 1 < len(sys.argv) and not sys.argv[idx+1].startswith("--"):
            domains = [d.strip() for d in sys.argv[idx+1].split(",")]

        # 默认: 四川21市州
        if not domains:
            domains = [
                "www.chengdu.gov.cn", "www.mianyang.gov.cn", "www.yibin.gov.cn",
                "www.deyang.gov.cn", "www.nanchong.gov.cn", "www.luzhou.gov.cn",
                "www.dazhou.gov.cn", "www.leshan.gov.cn", "www.zigong.gov.cn",
                "www.guangan.gov.cn", "www.ms.gov.cn", "www.suining.gov.cn",
                "www.neijiang.gov.cn", "www.guangyuan.gov.cn", "www.bazhong.gov.cn",
                "www.ziyang.gov.cn", "www.yaan.gov.cn", "www.panzhihua.gov.cn",
                "www.abazhou.gov.cn", "www.ganzi.gov.cn", "www.liangshan.gov.cn",
            ]
        print(f"信源探测器 v2.3.8 — 扫描{len(domains)}个域名...")
        batch = sd.discover_batch(domains, max_listings_per_domain=3)
        summary = batch["summary"]
        print(f"\n{'='*60}")
        print(f"  探测完成: {summary['domains_scanned']}个域名")
        print(f"  发现信源: {summary['total_discovered']}个列表页")
        print(f"  有产出的域名: {summary['domains_with_sources']}个")
        print(f"{'='*60}")
        for r in batch["results"]:
            if r["discovered"]:
                print(f"\n  [{r['domain']}]")
                for d in r["discovered"]:
                    print(f"    [{d['article_count']}篇] {d['title'][:50]}")
                    print(f"    {d['url']}")
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
        print("  python scripts/run_pipeline.py --crawl          深度爬取(文章页正文+质量门禁)")
        print("  python scripts/run_pipeline.py --crawl-and-feed 深度爬取+自动提取(含质量报告)")
        print("  python scripts/run_pipeline.py --search         智能搜索(缺口驱动)")
        print("  python scripts/run_pipeline.py --qc-only        质检补跑+就绪度联动")
        print("  python scripts/run_pipeline.py --relations-only 关系全量扫描")
        print("  python scripts/run_pipeline.py --premium-only   精品候选判定")
        print("  python scripts/run_pipeline.py --retry-failed   重试失败文件")
        print("  python scripts/run_pipeline.py --verify-sources 信源白名单状态")
        print("  python scripts/run_pipeline.py --full           一键全管道")


if __name__ == "__main__":
    main()
