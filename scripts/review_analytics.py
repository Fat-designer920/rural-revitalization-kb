"""
review_analytics.py - 审核反馈统计
路径：scripts/review_analytics.py
版本：v2.3.6-part1 - 版本统一

功能：
  - 统计各字段被修改的频率（哪些字段AI提取不准，人工改得最多）
  - 按知识类型分析修改率（哪类文件的提取质量较差）
  - 按Prompt版本对比修改率（版本升级后质量是否提升）
  - V3质检分数分布统计
  - 输出分析报告到控制台
"""
import os, sys, json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.db_manager import DatabaseManager


def run_analytics():
    db = DatabaseManager()
    conn = db.get_connection()
    c = conn.cursor()

    print(f"\n{'=' * 60}")
    print(f"  稻也 - 审核反馈统计")
    print(f"  分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

    # ================================================================
    # 1. 基础数据概览
    # ================================================================
    c.execute("SELECT COUNT(*) FROM knowledge_points")
    total_kps = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed'")
    confirmed = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM knowledge_points WHERE review_status='pending'")
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM knowledge_points WHERE review_status='ignored'")
    ignored = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM edit_history")
    total_edits = c.fetchone()[0]

    print(f"\n  [1] 基础数据")
    print(f"  {'-' * 50}")
    print(f"  知识点总数: {total_kps}")
    print(f"  已确认: {confirmed} | 待审核: {pending} | 已忽略: {ignored}")
    print(f"  编辑记录: {total_edits}条")

    if total_edits == 0:
        print(f"\n  暂无编辑记录,无法分析。")
        print(f"  请先审核一些知识点后再运行统计。")
        conn.close()
        return

    # ================================================================
    # 2. 字段修改频率（哪些字段AI提取不准）
    # ================================================================
    c.execute("SELECT edited_fields FROM edit_history WHERE edited_fields IS NOT NULL")
    field_counts = {}
    total_edit_records = 0
    for row in c.fetchall():
        fields_data = row[0]
        if not fields_data:
            continue
        try:
            if isinstance(fields_data, str):
                fields = json.loads(fields_data)
            else:
                fields = fields_data
            if isinstance(fields, dict):
                total_edit_records += 1
                for field_name in fields.keys():
                    field_counts[field_name] = field_counts.get(field_name, 0) + 1
        except (json.JSONDecodeError, ValueError):
            pass

    FIELD_LABELS = {
        "title": "标题",
        "final_category_id": "所属分类",
        "final_tags": "旧标签",
        "final_category_tags": "分类标签(L1)",
        "final_attribute_tags": "属性标签(L2)",
        "final_keywords": "关键词(L3)",
        "reviewer_notes": "审核备注",
        "original_excerpt": "原文摘录",
        "ai_extracted_content": "AI提取内容",
        "content_readiness": "就绪度",
        "source_authority": "权威度",
        "review_status": "审核状态",
    }

    print(f"\n  [2] 字段修改频率 (共{total_edit_records}次编辑)")
    print(f"  {'-' * 50}")
    if field_counts:
        sorted_fields = sorted(field_counts.items(), key=lambda x: -x[1])
        for fname, fcount in sorted_fields:
            label = FIELD_LABELS.get(fname, fname)
            pct = (fcount / total_edit_records * 100) if total_edit_records > 0 else 0
            bar = "#" * min(int(pct / 2), 30)
            print(f"  {label:16s} {fcount:4d}次 ({pct:5.1f}%) {bar}")
    else:
        print(f"  (无字段级修改数据)")

    # ================================================================
    # 3. 按知识类型分析修改率
    # ================================================================
    TYPE_NAMES = {
        "policy": "政策文件", "case": "项目案例", "experience": "操盘经验",
        "tool": "实操工具", "data": "数据资料"
    }

    c.execute("""
        SELECT kp.content_type,
               COUNT(DISTINCT kp.id) as total,
               COUNT(DISTINCT eh.knowledge_point_id) as edited
        FROM knowledge_points kp
        LEFT JOIN edit_history eh ON kp.id = eh.knowledge_point_id
        WHERE kp.review_status = 'confirmed'
        GROUP BY kp.content_type
    """)
    type_stats = c.fetchall()

    print(f"\n  [3] 按知识类型 - 修改率 (已确认的知识点)")
    print(f"  {'-' * 50}")
    if type_stats:
        for row in type_stats:
            ctype = row[0] or "unknown"
            total = row[1]
            edited = row[2]
            rate = (edited / total * 100) if total > 0 else 0
            label = TYPE_NAMES.get(ctype, ctype)
            print(f"  {label:10s} 共{total:3d}条, 修改{edited:3d}条 (修改率{rate:5.1f}%)")
    else:
        print(f"  (暂无已确认知识点)")

    # ================================================================
    # 4. 按Prompt版本对比
    # ================================================================
    c.execute("""
        SELECT kp.prompt_version,
               COUNT(kp.id) as total,
               SUM(CASE WHEN kp.review_status='confirmed' THEN 1 ELSE 0 END) as confirmed,
               SUM(CASE WHEN kp.review_status='ignored' THEN 1 ELSE 0 END) as ignored_count
        FROM knowledge_points kp
        WHERE kp.prompt_version IS NOT NULL AND kp.prompt_version != ''
        GROUP BY kp.prompt_version
        ORDER BY kp.prompt_version
    """)
    version_stats = c.fetchall()

    print(f"\n  [4] 按Prompt版本对比")
    print(f"  {'-' * 50}")
    if version_stats:
        for row in version_stats:
            ver = row[0] or "(空)"
            total = row[1]
            conf = row[2]
            ign = row[3]
            conf_rate = (conf / total * 100) if total > 0 else 0
            ign_rate = (ign / total * 100) if total > 0 else 0
            print(f"  {ver:14s} 共{total:3d}条 | 确认{conf:3d}({conf_rate:4.1f}%) | 忽略{ign:3d}({ign_rate:4.1f}%)")
    else:
        print(f"  (暂无版本追踪数据)")

    # ================================================================
    # 5. V3质检分数分布
    # ================================================================
    c.execute("""
        SELECT qa_score, COUNT(*) as cnt
        FROM knowledge_points
        WHERE qa_score IS NOT NULL
        GROUP BY qa_score
        ORDER BY qa_score
    """)
    qa_stats = c.fetchall()

    c.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score IS NULL")
    no_qa = c.fetchone()[0]

    print(f"\n  [5] V3质检分数分布")
    print(f"  {'-' * 50}")
    if qa_stats:
        total_scored = sum(row[1] for row in qa_stats)
        avg_score = sum(row[0] * row[1] for row in qa_stats) / total_scored if total_scored > 0 else 0
        print(f"  已质检: {total_scored}条 | 未质检: {no_qa}条 | 平均分: {avg_score:.1f}")
        for row in qa_stats:
            score = row[0]
            cnt = row[1]
            pct = (cnt / total_scored * 100) if total_scored > 0 else 0
            bar = "#" * min(int(pct), 30)
            label = {1: "极差", 2: "较差", 3: "中等", 4: "良好", 5: "优秀"}.get(score, str(score))
            print(f"  {score}分({label:4s}) {cnt:4d}条 ({pct:5.1f}%) {bar}")
    else:
        print(f"  暂无质检数据(共{no_qa}条未质检)")

    # ================================================================
    # 6. 质检问题标记 TOP
    # ================================================================
    c.execute("SELECT qa_flags FROM knowledge_points WHERE qa_flags IS NOT NULL AND qa_flags != '' AND qa_flags != '[]'")
    flag_counts = {}
    for row in c.fetchall():
        flags_data = row[0]
        try:
            if isinstance(flags_data, str):
                flags = json.loads(flags_data)
            else:
                flags = flags_data
            if isinstance(flags, list):
                for flag in flags:
                    if isinstance(flag, str) and flag:
                        flag_counts[flag] = flag_counts.get(flag, 0) + 1
        except (json.JSONDecodeError, ValueError):
            pass

    FLAG_LABELS = {
        "independence": "独立性不足(脱离原文难理解)",
        "density": "信息密度低(缺乏具体数据/方法)",
        "granularity_coarse": "颗粒度过粗(一条讲了多件事)",
        "granularity_fine": "颗粒度过细(一条信息太碎)",
        "tag_mismatch": "标签不符(标签与内容不一致)",
        "duplicate_suspect": "疑似重复(与同文件其他条高度相似)",
    }

    print(f"\n  [6] 质检问题分布")
    print(f"  {'-' * 50}")
    if flag_counts:
        sorted_flags = sorted(flag_counts.items(), key=lambda x: -x[1])
        for flag, cnt in sorted_flags:
            label = FLAG_LABELS.get(flag, flag)
            print(f"  {cnt:4d}次 - {label}")
    else:
        print(f"  (暂无质检问题标记)")

    # ================================================================
    # 总结与建议
    # ================================================================
    print(f"\n  {'=' * 50}")
    print(f"  [总结与建议]")
    print(f"  {'=' * 50}")

    if field_counts:
        top_field = max(field_counts.items(), key=lambda x: x[1])
        top_label = FIELD_LABELS.get(top_field[0], top_field[0])
        print(f"  - 修改最多的字段: {top_label} ({top_field[1]}次)")
        print(f"    => 建议优化对应Prompt的输出指令")

    if flag_counts:
        top_flag = max(flag_counts.items(), key=lambda x: x[1])
        top_flag_label = FLAG_LABELS.get(top_flag[0], top_flag[0])
        print(f"  - 最常见的质检问题: {top_flag_label} ({top_flag[1]}次)")

    if qa_stats and total_scored > 0:
        low_count = sum(row[1] for row in qa_stats if row[0] <= 2)
        if low_count > 0:
            print(f"  - {low_count}条知识点质检评分<=2, 建议优先审核处理")

    print(f"\n{'=' * 60}")

    conn.close()


# ================================================================
# v2.1.2 新增：供API调用的JSON版统计（不print，返回结构化数据）
# ================================================================
def get_analytics_json():
    """
    执行审核反馈统计，返回结构化JSON结果。
    供api_server.py的/api/tools/review-analytics端点调用。
    """
    db = DatabaseManager()
    conn = db.get_connection()
    c = conn.cursor()
    result = {"analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    # 1. 基础数据
    c.execute("SELECT COUNT(*) FROM knowledge_points")
    total_kps = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed'")
    confirmed = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM knowledge_points WHERE review_status='pending'")
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM knowledge_points WHERE review_status='ignored'")
    ignored = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM edit_history")
    total_edits = c.fetchone()[0]
    result["overview"] = {
        "total": total_kps, "confirmed": confirmed,
        "pending": pending, "ignored": ignored, "edits": total_edits
    }

    # 2. 字段修改频率
    FIELD_LABELS = {
        "title": "标题", "final_category_id": "所属分类", "final_tags": "旧标签",
        "final_category_tags": "分类标签(L1)", "final_attribute_tags": "属性标签(L2)",
        "final_keywords": "关键词(L3)", "reviewer_notes": "审核备注",
        "original_excerpt": "原文摘录", "ai_extracted_content": "AI提取内容",
        "content_readiness": "就绪度", "source_authority": "权威度", "review_status": "审核状态",
    }
    c.execute("SELECT edited_fields FROM edit_history WHERE edited_fields IS NOT NULL")
    field_counts = {}
    total_edit_records = 0
    for row in c.fetchall():
        fields_data = row[0]
        if not fields_data:
            continue
        try:
            fields = json.loads(fields_data) if isinstance(fields_data, str) else fields_data
            if isinstance(fields, dict):
                total_edit_records += 1
                for fn in fields.keys():
                    field_counts[fn] = field_counts.get(fn, 0) + 1
        except (json.JSONDecodeError, ValueError):
            pass
    field_list = []
    for fn, cnt in sorted(field_counts.items(), key=lambda x: -x[1]):
        pct = (cnt * 100.0 / total_edit_records) if total_edit_records > 0 else 0
        field_list.append({"field": fn, "label": FIELD_LABELS.get(fn, fn), "count": cnt, "pct": round(pct, 1)})
    result["field_edits"] = {"total_records": total_edit_records, "fields": field_list}

    # 3. 按类型修改率
    TYPE_NAMES = {"policy": "政策文件", "case": "项目案例", "experience": "操盘经验",
                  "tool": "实操工具", "data": "数据资料"}
    c.execute("""SELECT kp.content_type, COUNT(DISTINCT kp.id) as total,
                 COUNT(DISTINCT eh.knowledge_point_id) as edited
                 FROM knowledge_points kp
                 LEFT JOIN edit_history eh ON kp.id = eh.knowledge_point_id
                 WHERE kp.review_status = 'confirmed' GROUP BY kp.content_type""")
    type_list = []
    for row in c.fetchall():
        ct = row[0] or "unknown"
        total = row[1]
        edited = row[2]
        rate = (edited * 100.0 / total) if total > 0 else 0
        type_list.append({"type": ct, "label": TYPE_NAMES.get(ct, ct),
                          "total": total, "edited": edited, "rate": round(rate, 1)})
    result["type_edit_rates"] = type_list

    # 4. 按Prompt版本
    c.execute("""SELECT kp.prompt_version, COUNT(kp.id) as total,
                 SUM(CASE WHEN kp.review_status='confirmed' THEN 1 ELSE 0 END) as confirmed,
                 SUM(CASE WHEN kp.review_status='ignored' THEN 1 ELSE 0 END) as ignored_count
                 FROM knowledge_points kp
                 WHERE kp.prompt_version IS NOT NULL AND kp.prompt_version != ''
                 GROUP BY kp.prompt_version ORDER BY kp.prompt_version""")
    ver_list = []
    for row in c.fetchall():
        ver_list.append({"version": row[0], "total": row[1], "confirmed": row[2], "ignored": row[3]})
    result["prompt_versions"] = ver_list

    # 5. 质检分数分布
    c.execute("SELECT qa_score, COUNT(*) FROM knowledge_points WHERE qa_score IS NOT NULL GROUP BY qa_score ORDER BY qa_score")
    qa_list = []
    score_labels = {1: "极差", 2: "较差", 3: "中等", 4: "良好", 5: "优秀"}
    for row in c.fetchall():
        qa_list.append({"score": row[0], "label": score_labels.get(row[0], str(row[0])), "count": row[1]})
    c.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score IS NULL")
    no_qa = c.fetchone()[0]
    result["qa_distribution"] = {"scored": qa_list, "unscored": no_qa}

    # 6. 质检问题分布
    FLAG_LABELS = {
        "independence": "独立性不足", "density": "信息密度低",
        "granularity_coarse": "颗粒度过粗", "granularity_fine": "颗粒度过细",
        "tag_mismatch": "标签不符", "duplicate_suspect": "疑似重复",
    }
    c.execute("SELECT qa_flags FROM knowledge_points WHERE qa_flags IS NOT NULL AND qa_flags != '' AND qa_flags != '[]'")
    flag_counts = {}
    for row in c.fetchall():
        try:
            flags = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            if isinstance(flags, list):
                for fl in flags:
                    if isinstance(fl, str) and fl:
                        flag_counts[fl] = flag_counts.get(fl, 0) + 1
        except (json.JSONDecodeError, ValueError):
            pass
    flag_list = []
    for fl, cnt in sorted(flag_counts.items(), key=lambda x: -x[1]):
        flag_list.append({"flag": fl, "label": FLAG_LABELS.get(fl, fl), "count": cnt})
    result["qa_flags"] = flag_list

    conn.close()
    return result


def main():
    try:
        run_analytics()
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        import traceback
        traceback.print_exc()
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
