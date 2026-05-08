"""
benchmark_system.py - QA系统基准评测引擎
路径：scripts/benchmark_system.py
版本：v2.3.7-part7
4维评测(accuracy/completeness/timeliness/source_traceability) + 历史对比
"""
import os, sys, json, time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class BenchmarkEngine:
    """QA评测基准引擎: 加载50条测试查询 → 逐条跑QA → 4维打分 → 报告."""

    DIMENSIONS = ["accuracy", "completeness", "timeliness", "source_traceability"]

    def __init__(self, db: Any = None, client: Any = None):
        self.db = db
        self.client = client
        self.results: List[Dict] = []
        self.run_ts: str = ""
        self._queries: List[Dict] = []

    def load_queries(self, path: str = None) -> List[Dict]:
        """加载测试查询JSON, 期望 [{category, query, gold_score?}, ...]."""
        if path is None:
            path = str(PROJECT_ROOT / "data" / "debug" / "test_queries_50.json")
        with open(path, "r", encoding="utf-8") as f:
            self._queries = json.load(f)
        return self._queries

    def run_benchmark(self, queries: List[Dict] = None,
                      sample_limit: int = 0,
                      gold_mode: bool = False) -> Dict:
        """执行全部(或前sample_limit条)测试查询, 逐条跑QA+打分.

        gold_mode: 若查询自带gold_score则对比, 否则仅auto_score.
        返回顶层报告 dict.
        """
        if queries is None:
            queries = self._queries
        if not queries:
            return {"ok": False, "error": "no queries loaded"}

        if not self.db or not self.client:
            return {"ok": False, "error": "db/client not initialized"}

        target = queries[:sample_limit] if sample_limit > 0 else queries
        self.run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results = []

        from scripts.qa_assistant import run_qa

        for i, item in enumerate(target):
            q = str(item.get("query", "")).strip()
            cat = item.get("category", "未分类")
            gold = item.get("gold_score") if gold_mode else None
            if not q:
                continue

            t0 = time.time()
            try:
                qa_result = run_qa(
                    self.db, self.client, q,
                    mode="self", is_test_query=1, model_pref="v3",
                )
            except Exception as e:
                qa_result = {"ok": False, "error": str(e)[:300]}

            latency_ms = int((time.time() - t0) * 1000)
            scores = self._score_result(qa_result, latency_ms, gold)

            self.results.append({
                "index": i,
                "category": cat,
                "query": q[:200],
                "qa_ok": qa_result.get("ok", False),
                "source": qa_result.get("source", "unknown"),
                "latency_ms": latency_ms,
                "scores": scores,
                "has_gold": gold is not None,
                "gold_score": gold,
            })

        return self._build_report()

    def _score_result(self, qa_result: Dict, latency_ms: int,
                      gold: Optional[Dict] = None) -> Dict:
        """4维启发式打分(0-5), 有gold则计算delta."""
        answer = qa_result.get("answer") or {}
        direct = str(answer.get("direct_answer", "")) if isinstance(answer, dict) else str(answer)
        ev_ids = answer.get("evidence_kp_ids", []) if isinstance(answer, dict) else []
        gap = str(answer.get("coverage_gap", "")) if isinstance(answer, dict) else ""
        policy_basis = answer.get("policy_basis", []) if isinstance(answer, dict) else []
        source_label = qa_result.get("source", "rule_fallback")

        accuracy = 3
        if source_label == "rule_fallback":
            accuracy = max(1, accuracy - 2)
        if ev_ids:
            accuracy = min(5, accuracy + min(len(ev_ids), 2))
        if direct and len(direct) >= 80:
            accuracy = min(5, accuracy + 1)

        completeness = 3
        if direct and len(direct) >= 50:
            completeness += 1
        if answer.get("followup_questions") if isinstance(answer, dict) else False:
            completeness += 1
        if gap and "无法充分覆盖" not in gap:
            completeness = min(5, completeness + 1)
        completeness = max(1, min(5, completeness))

        timeliness = 3
        if answer and isinstance(answer, dict) and answer.get("policy_basis"):
            timeliness = min(5, timeliness + 1)
        if latency_ms < 5000:
            timeliness = min(5, timeliness + 1)
        if latency_ms < 2000:
            timeliness = min(5, timeliness + 1)

        traceability = 1
        if policy_basis:
            traceability = min(3, len(policy_basis))
        if ev_ids:
            traceability = min(5, traceability + min(len(ev_ids), 2))
        if isinstance(answer, dict) and answer.get("evidence_kp_ids"):
            traceability = min(5, traceability + 1)

        scores = {
            "accuracy": accuracy,
            "completeness": completeness,
            "timeliness": timeliness,
            "source_traceability": traceability,
            "overall": round((accuracy + completeness + timeliness + traceability) / 4, 1),
        }

        if gold:
            delta = {}
            for d in self.DIMENSIONS:
                gv = gold.get(d, 3)
                delta[d] = scores[d] - gv
            delta["overall"] = round(
                (delta["accuracy"] + delta["completeness"]
                 + delta["timeliness"] + delta["source_traceability"]) / 4, 1
            )
            scores["delta_vs_gold"] = delta
            scores["gold_available"] = True

        return scores

    def _build_report(self) -> Dict:
        """聚合结果生成顶层报告."""
        if not self.results:
            return {"ok": False, "error": "no results"}

        total = len(self.results)
        ok_count = sum(1 for r in self.results if r["qa_ok"])
        dim_sums = {d: 0.0 for d in self.DIMENSIONS}
        dim_sums["overall"] = 0.0
        cat_scores: Dict[str, List[float]] = {}

        for r in self.results:
            s = r["scores"]
            for d in self.DIMENSIONS:
                dim_sums[d] += s.get(d, 0)
            dim_sums["overall"] += s.get("overall", 0)
            cat = r.get("category", "未分类")
            cat_scores.setdefault(cat, []).append(s.get("overall", 0))

        avg = {k: round(v / total, 2) for k, v in dim_sums.items()}
        by_category = {}
        for cat, ovs in sorted(cat_scores.items()):
            by_category[cat] = {
                "count": len(ovs),
                "avg_overall": round(sum(ovs) / len(ovs), 2),
                "min_overall": round(min(ovs), 2),
                "max_overall": round(max(ovs), 2),
            }

        gold_count = sum(1 for r in self.results if r.get("has_gold"))
        gold_delta = None
        if gold_count > 0:
            gold_deltas = []
            for r in self.results:
                if r.get("has_gold") and r["scores"].get("delta_vs_gold"):
                    gold_deltas.append(r["scores"]["delta_vs_gold"]["overall"])
            if gold_deltas:
                gold_delta = {
                    "avg": round(sum(gold_deltas) / len(gold_deltas), 2),
                    "count": len(gold_deltas),
                }

        return {
            "ok": True,
            "run_ts": self.run_ts,
            "total_queries": total,
            "ok_count": ok_count,
            "fail_count": total - ok_count,
            "avg_scores": avg,
            "by_category": by_category,
            "gold_comparison": gold_delta,
            "results": self.results,
        }

    def save_report(self, report: Dict, output_dir: str = None) -> str:
        """存JSON报告到 data/benchmarks/ 返回路径."""
        if output_dir is None:
            output_dir = str(PROJECT_ROOT / "data" / "benchmarks")
        os.makedirs(output_dir, exist_ok=True)
        ts = report.get("run_ts") or datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = "benchmark_%s.json" % ts
        fpath = os.path.join(output_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        return fpath

    def generate_markdown(self, report: Dict) -> str:
        """生成Markdown评测摘要."""
        if not report.get("ok"):
            return "# Benchmark Report\n\n**FAILED**: %s" % report.get("error", "unknown")

        lines = [
            "# QA Benchmark Report",
            "",
            "**Run**: %s | **Total**: %d queries | **Passed**: %d | **Failed**: %d" % (
                report["run_ts"], report["total_queries"],
                report["ok_count"], report["fail_count"],
            ),
            "",
            "## Average Scores (0-5)",
            "",
            "| Dimension | Score |",
            "|-----------|-------|",
        ]
        for d in self.DIMENSIONS:
            lines.append("| %s | %.2f |" % (d.replace("_", " ").title(), report["avg_scores"][d]))
        lines.append("| **Overall** | **%.2f** |" % report["avg_scores"]["overall"])

        if report.get("gold_comparison"):
            gd = report["gold_comparison"]
            lines.extend([
                "",
                "## Gold Standard Comparison",
                "",
                "- Queries with gold scores: %d" % gd["count"],
                "- Avg delta vs gold: %+.2f" % gd["avg"],
            ])

        lines.extend(["", "## By Category", "", "| Category | Count | Avg | Min | Max |", "|----------|-------|-----|-----|-----|"])
        for cat, stats in sorted(report.get("by_category", {}).items()):
            lines.append("| %s | %d | %.2f | %.2f | %.2f |" % (
                cat, stats["count"], stats["avg_overall"],
                stats["min_overall"], stats["max_overall"],
            ))

        lines.extend([
            "",
            "## Worst 5 Queries",
            "",
            "| # | Query | Overall |",
            "|---|-------|---------|",
        ])
        worst = sorted(report.get("results", []),
                       key=lambda r: r["scores"].get("overall", 0))[:5]
        for r in worst:
            lines.append("| %d | %s | %.1f |" % (
                r["index"], r["query"][:60], r["scores"].get("overall", 0),
            ))

        lines.extend([
            "",
            "## Best 5 Queries",
            "",
            "| # | Query | Overall |",
            "|---|-------|---------|",
        ])
        best = sorted(report.get("results", []),
                      key=lambda r: r["scores"].get("overall", 0), reverse=True)[:5]
        for r in best:
            lines.append("| %d | %s | %.1f |" % (
                r["index"], r["query"][:60], r["scores"].get("overall", 0),
            ))

        lines.append("\n---\n*Generated by benchmark_system.py*")
        return "\n".join(lines)


def compare_benchmarks(report1: Dict, report2: Dict) -> Dict:
    """对比两次benchmark, 返回变化量."""
    a1 = report1.get("avg_scores", {})
    a2 = report2.get("avg_scores", {})
    diffs = {}
    for d in BenchmarkEngine.DIMENSIONS + ("overall",):
        v1 = a1.get(d, 0)
        v2 = a2.get(d, 0)
        diffs[d] = round(v2 - v1, 2)
    return {
        "run1_ts": report1.get("run_ts", "?"),
        "run2_ts": report2.get("run_ts", "?"),
        "deltas": diffs,
        "improved": diffs.get("overall", 0) > 0,
        "queries1": report1.get("total_queries", 0),
        "queries2": report2.get("total_queries", 0),
    }


def load_benchmark(path: str) -> Dict:
    """加载历史benchmark JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    """CLI入口: python scripts/benchmark_system.py [--sample N] [--gold]"""
    import argparse
    ap = argparse.ArgumentParser(description="QA Benchmark System")
    ap.add_argument("--sample", type=int, default=0, help="仅跑前N条(0=全部)")
    ap.add_argument("--gold", action="store_true", help="启用gold standard对比")
    ap.add_argument("--queries", type=str, default=None, help="测试查询JSON路径")
    ap.add_argument("--compare", type=str, nargs=2, default=None,
                    help="对比两个历史benchmark JSON")
    ap.add_argument("--output-dir", type=str, default=None)
    args = ap.parse_args()

    if args.compare:
        r1 = load_benchmark(args.compare[0])
        r2 = load_benchmark(args.compare[1])
        cmp_result = compare_benchmarks(r1, r2)
        print(json.dumps(cmp_result, ensure_ascii=False, indent=2))
        return

    from scripts.db_manager import DatabaseManager
    from scripts.deepseek_client import DeepSeekClient

    db = DatabaseManager()
    client = DeepSeekClient()

    engine = BenchmarkEngine(db, client)
    queries = engine.load_queries(args.queries)
    print("Loaded %d test queries" % len(queries))

    report = engine.run_benchmark(queries, sample_limit=args.sample, gold_mode=args.gold)
    if report.get("ok"):
        fpath = engine.save_report(report, args.output_dir)
        print("Report saved: %s" % fpath)
        md = engine.generate_markdown(report)
        md_path = fpath.replace(".json", ".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)
        print("Markdown: %s" % md_path)
        print("\n" + md[:2000])
    else:
        print("Benchmark FAILED: %s" % report.get("error", "unknown"))


if __name__ == "__main__":
    main()
