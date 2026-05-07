"""
qa_stress_test.py - 模拟真实用户问答测试(课程体系问题驱动)
路径：scripts/qa_stress_test.py
版本：v2.3.7-part2

用课程体系20个核心问题模拟操盘手提问, 评估:
- 检索命中率(有没有相关知识?)
- 回答可用性(操盘手能用吗?)
- 幻觉风险(AI有没有编造?)
- 知识缺口(KB缺什么?)

输出运营报告→指导喂料方向+软件迭代需求。
"""
import sys, json, time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "agents"))
sys.path.insert(0, str(PROJECT_ROOT))


def load_test_questions():
    """从课程体系加载测试问题,覆盖5个模块各取代表性问题。"""
    from course_system import get_course_system
    cs = get_course_system()
    questions = []
    for mod in cs["modules"]:
        for les in mod["lessons"]:
            questions.append({
                "module": mod["title"],
                "module_id": mod["id"],
                "lesson": les["title"],
                "lesson_id": les["id"],
                "question": les["core_question"],
                "knowledge_needs": les.get("knowledge_needs", []),
                "test_category": "core_question",
            })
    # 选代表: 每模块至少1题, 共8题覆盖全场景
    selected = []
    module_picks = {"M1": [0, 3], "M2": [4, 8], "M3": [9], "M4": [13], "M5": [16, 19]}
    for mod_id, indices in module_picks.items():
        mod_qs = [q for q in questions if q["module_id"] == mod_id]
        for idx in indices:
            if idx < len(mod_qs):
                selected.append(mod_qs[idx])
    return selected


def run_qa_test(db, client, questions):
    """运行问答测试并收集结果。"""
    from qa_assistant import run_qa as qa_run

    results = []
    for i, q in enumerate(questions):
        t0 = time.time()
        try:
            resp = qa_run(db=db, client=client, query=q["question"], mode="self", is_test_query=1)
            elapsed = time.time() - t0

            answer_panels = resp.get("answer") or {}
            evidence_ids = answer_panels.get("evidence_kp_ids", []) if isinstance(answer_panels, dict) else []
            retrieved = resp.get("retrieved_kp_ids", [])

            results.append({
                "index": i + 1,
                "module": q["module"],
                "lesson": q["lesson"],
                "question": q["question"],
                "knowledge_needs": q["knowledge_needs"][:3],
                "direct_answer": answer_panels.get("direct_answer", "")[:500] if isinstance(answer_panels, dict) else "",
                "coverage_gap": answer_panels.get("coverage_gap", "") if isinstance(answer_panels, dict) else "",
                "evidence_count": len(evidence_ids),
                "retrieved_count": len(retrieved),
                "source": resp.get("source", "unknown"),
                "latency_ms": resp.get("latency_ms", 0),
                "cost_estimate_cny": resp.get("cost_estimate_cny", 0),
                "ok": resp.get("ok", False),
                "error": resp.get("error", ""),
            })
        except Exception as e:
            results.append({
                "index": i + 1,
                "module": q["module"],
                "lesson": q["lesson"],
                "question": q["question"],
                "ok": False,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            })

        time.sleep(2)

    return results


def grade_results(results, db):
    """评估测试结果,生成运营洞察。"""
    report = {
        "test_time": datetime.now().isoformat(),
        "total_questions": len(results),
        "ok_count": sum(1 for r in results if r.get("ok")),
        "fail_count": sum(1 for r in results if not r.get("ok")),
        "avg_evidence_count": sum(r.get("evidence_count", 0) for r in results) / max(1, len(results)),
        "avg_retrieved_count": sum(r.get("retrieved_count", 0) for r in results) / max(1, len(results)),
        "avg_latency_ms": sum(r.get("latency_ms", 0) for r in results) / max(1, len(results)),
        "total_cost_estimate": sum(r.get("cost_estimate_cny", 0) for r in results),
        "by_source": {},
        "software_issues": [],
        "knowledge_gaps": [],
        "per_question": results,
    }

    # 按source统计
    for r in results:
        src = r.get("source", "unknown")
        report["by_source"][src] = report["by_source"].get(src, 0) + 1

    # 软件问题检测
    for r in results:
        if not r.get("ok"):
            report["software_issues"].append({
                "severity": "error",
                "question": r["question"][:80],
                "issue": r.get("error", "未知错误"),
                "suggestion": "检查QA引擎降级链+API连通性",
            })
        if r.get("source") in ("rule_fallback", "r1_fallback"):
            report["software_issues"].append({
                "severity": "warning",
                "question": r["question"][:80],
                "issue": f"降级到{r['source']},可能影响回答质量",
                "suggestion": "检查主链V3是否有稳定性问题",
            })
        if r.get("evidence_count", 0) == 0 and r.get("ok"):
            report["software_issues"].append({
                "severity": "info",
                "question": r["question"][:80],
                "issue": "无evidence引用,可能AI在凭常识回答",
                "suggestion": "加强evidence_kp_ids强制子集校验",
            })

    # 知识缺口分析
    for r in results:
        if r.get("coverage_gap"):
            report["knowledge_gaps"].append({
                "question": r["question"][:100],
                "gap": r["coverage_gap"],
                "needed_knowledge": r.get("knowledge_needs", []),
                "evidence_count": r.get("evidence_count", 0),
            })
        elif r.get("evidence_count", 0) < 2:
            report["knowledge_gaps"].append({
                "question": r["question"][:100],
                "gap": f"仅{r.get('evidence_count',0)}条evidence,KB覆盖可能不足",
                "needed_knowledge": r.get("knowledge_needs", []),
                "evidence_count": r.get("evidence_count", 0),
            })

    # 喂料优先级(从知识缺口反推)
    feed_priority = {}
    for gap in report["knowledge_gaps"]:
        for need in gap.get("needed_knowledge", []):
            feed_priority[need] = feed_priority.get(need, 0) + 1
    report["feed_priorities"] = sorted(feed_priority.items(), key=lambda x: x[1], reverse=True)[:15]

    return report


def main():
    from db_manager import DatabaseManager
    from deepseek_client import DeepSeekClient

    print("=" * 60)
    print("  稻也 - 模拟问答运营测试")
    print("=" * 60)

    # 初始化
    db = DatabaseManager()
    db.init_tables()
    config_path = PROJECT_ROOT / "config" / "settings.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    client = DeepSeekClient(config)

    # 检查KB就绪度
    conn = db.get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM knowledge_points")
    total_kp = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM knowledge_points WHERE content_readiness IN ('quotable','premium')")
    usable_kp = c.fetchone()[0]
    conn.close()
    print(f"\nKB状态: {total_kp}条KP, {usable_kp}条可引用(quotable+premium)")
    if usable_kp < 50:
        print("WARNING: 可引用KP不足50条, 问答质量将受限。先跑管道扩充KB。")
        return

    # 加载问题
    questions = load_test_questions()
    print(f"测试问题: {len(questions)}个(覆盖5模块)")

    # 运行测试(前5题,避免费用过高)
    print("\n开始运行问答测试...")
    test_batch = questions[:8]  # 8题覆盖全场景
    results = run_qa_test(db, client, test_batch)

    # 评估
    report = grade_results(results, db)

    # 输出报告
    print("\n" + "=" * 60)
    print("  运营测试报告")
    print("=" * 60)
    print(f"测试问题: {report['total_questions']}个")
    print(f"成功: {report['ok_count']} / 失败: {report['fail_count']}")
    print(f"平均evidence数: {report['avg_evidence_count']:.1f}")
    print(f"平均检索数: {report['avg_retrieved_count']:.1f}")
    print(f"平均延迟: {report['avg_latency_ms']:.0f}ms")
    print(f"估算总费用: {report['total_cost_estimate']:.3f} yuan")
    print(f"降级分布: {report['by_source']}")

    if report["software_issues"]:
        print(f"\n--- 软件问题({len(report['software_issues'])}个) ---")
        for si in report["software_issues"][:8]:
            print(f"  [{si['severity']}] {si['issue'][:100]}")
            print(f"    建议: {si['suggestion']}")

    if report["knowledge_gaps"]:
        print(f"\n--- 知识缺口({len(report['knowledge_gaps'])}个) ---")
        for kg in report["knowledge_gaps"][:8]:
            gap_text = kg.get("gap", "")[:120]
            print(f"  Q: {kg['question'][:80]}")
            if gap_text:
                print(f"  Gap: {gap_text}")
            print(f"  Evidence: {kg['evidence_count']}条")

    if report["feed_priorities"]:
        print(f"\n--- 喂料优先级(Top 10) ---")
        for i, (need, count) in enumerate(report["feed_priorities"][:10], 1):
            print(f"  {i}. [{count}次命中] {need}")

    # 保存完整报告
    report_path = PROJECT_ROOT / "logs" / "qa_test_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n完整报告: {report_path}")

    return report


if __name__ == "__main__":
    main()
