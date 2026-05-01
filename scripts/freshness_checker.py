"""
freshness_checker.py - 知识点保鲜检查器
路径：scripts/freshness_checker.py
版本：v2.3.6-part1
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent


def _load_config():
    p = PROJECT_ROOT / "config" / "settings.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _get_db_path(config=None):
    if config:
        return config.get("database_path",
                          str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db"))
    return str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")


def _get_freshness_rules():
    """从tag_config.py加载保鲜周期规则"""
    try:
        from scripts.tag_config import FRESHNESS_RULES, FRESHNESS_OVERDUE_DAYS
        return FRESHNESS_RULES, FRESHNESS_OVERDUE_DAYS
    except ImportError:
        try:
            from tag_config import FRESHNESS_RULES, FRESHNESS_OVERDUE_DAYS
            return FRESHNESS_RULES, FRESHNESS_OVERDUE_DAYS
        except ImportError:
            # 兜底默认值
            return {
                "1": 90, "2": 180, "3": 365, "4": 365, "5": 90
            }, 30


def _get_category_level1_map(conn):
    """获取 category_id -> level1_code 的映射"""
    cur = conn.cursor()
    cur.execute("SELECT id, level1_code FROM categories")
    return {row[0]: row[1] for row in cur.fetchall()}


def _content_type_to_level1(content_type):
    """content_type -> level1_code 的映射"""
    mapping = {
        "policy": "1",
        "case": "2",
        "experience": "3",
        "tool": "4",
        "data": "5"
    }
    return mapping.get(content_type, "3")  # 默认经验类


def _get_default_interval(content_type):
    """根据content_type获取默认保鲜周期"""
    rules, _ = _get_freshness_rules()
    level1 = _content_type_to_level1(content_type)
    return rules.get(level1, 180)


def auto_fill_intervals(conn):
    """为缺少保鲜周期的已确认知识点自动赋默认值"""
    rules, _ = _get_freshness_rules()
    cur = conn.cursor()

    # 查找 freshness_interval_days 仍为建表默认值180且从未人工修改过的记录
    # 策略：只更新从未检查过且interval=180（建表默认值）的记录
    cur.execute("""
        SELECT id, content_type, freshness_interval_days
        FROM knowledge_points
        WHERE review_status = 'confirmed'
          AND freshness_checked_at IS NULL
    """)
    rows = cur.fetchall()

    updated = 0
    for row in rows:
        kp_id, ct, current_interval = row
        expected = _get_default_interval(ct)
        if current_interval != expected:
            cur.execute(
                "UPDATE knowledge_points SET freshness_interval_days=? WHERE id=?",
                (expected, kp_id)
            )
            updated += 1

    if updated > 0:
        conn.commit()
    return updated


def scan_freshness(db_path=None):
    """
    扫描所有已确认知识点的保鲜状态

    返回: {
        "total_confirmed": int,
        "stale": int,          # 已到期(含逾期)
        "overdue": int,        # 逾期未检(超期>OVERDUE_DAYS天)
        "due_7d": int,         # 7天内到期
        "due_30d": int,        # 30天内到期
        "ok": int,             # 保鲜有效
        "overdue_items": [...],
        "stale_items": [...],
        "due_7d_items": [...],
        "due_30d_items": [...]
    }
    """
    if not db_path:
        config = _load_config()
        db_path = _get_db_path(config)

    if not Path(db_path).exists():
        return {"total_confirmed": 0, "stale": 0, "overdue": 0,
                "due_7d": 0, "due_30d": 0, "ok": 0,
                "overdue_items": [], "stale_items": [],
                "due_7d_items": [], "due_30d_items": []}

    _, overdue_days = _get_freshness_rules()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 自动补齐保鲜周期
    auto_filled = auto_fill_intervals(conn)

    cur = conn.cursor()

    # 查询所有已确认知识点的保鲜相关字段
    cur.execute("""
        SELECT kp.id, kp.title, kp.content_type,
               kp.freshness_checked_at, kp.freshness_interval_days,
               kp.created_at, kp.confirmed_at, kp.freshness_note,
               cat.level1_name, cat.level2_name
        FROM knowledge_points kp
        LEFT JOIN categories cat ON COALESCE(kp.final_category_id, kp.suggested_category_id) = cat.id
        WHERE kp.review_status = 'confirmed'
          AND kp.is_outdated = 0
        ORDER BY kp.id
    """)

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    now = datetime.now()
    type_names = {
        "policy": "政策", "case": "案例", "experience": "经验",
        "tool": "工具", "data": "数据"
    }

    result = {
        "total_confirmed": len(rows),
        "stale": 0, "overdue": 0, "due_7d": 0, "due_30d": 0, "ok": 0,
        "auto_filled": auto_filled,
        "overdue_items": [], "stale_items": [],
        "due_7d_items": [], "due_30d_items": []
    }

    for row in rows:
        interval = row["freshness_interval_days"] or 180

        # 确定起算时间点
        check_time = row["freshness_checked_at"]
        if check_time:
            try:
                base = datetime.strptime(check_time, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                base = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        else:
            # 从未检查过，以created_at为起算点
            try:
                base = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                continue

        days_since = (now - base).days
        days_remaining = interval - days_since

        item = {
            "id": row["id"],
            "title": row["title"],
            "type": type_names.get(row["content_type"], row["content_type"]),
            "category": (row["level1_name"] or "") + "/" + (row["level2_name"] or ""),
            "interval": interval,
            "last_checked": row["freshness_checked_at"] or "(从未检查)",
            "days_overdue": max(0, -days_remaining),
            "days_remaining": days_remaining,
            "note": row["freshness_note"] or ""
        }

        if days_remaining <= -overdue_days:
            # 逾期未检
            result["overdue"] += 1
            result["stale"] += 1
            result["overdue_items"].append(item)
        elif days_remaining < 0:
            # 已到期但未超过逾期阈值
            result["stale"] += 1
            result["stale_items"].append(item)
        elif days_remaining <= 7:
            # 7天内到期
            result["due_7d"] += 1
            result["due_7d_items"].append(item)
        elif days_remaining <= 30:
            # 30天内到期
            result["due_30d"] += 1
            result["due_30d_items"].append(item)
        else:
            result["ok"] += 1

    # 按紧急度排序（逾期天数多的在前）
    result["overdue_items"].sort(key=lambda x: -x["days_overdue"])
    result["stale_items"].sort(key=lambda x: -x["days_overdue"])

    return result


def get_freshness_summary(db_path=None):
    """供api_server.py调用的简要统计（不含详细列表）"""
    full = scan_freshness(db_path)
    return {
        "total_confirmed": full["total_confirmed"],
        "stale": full["stale"],
        "overdue": full["overdue"],
        "due_7d": full["due_7d"],
        "due_30d": full["due_30d"],
        "ok": full["ok"]
    }


def get_stale_list(db_path=None, limit=50):
    """供api_server.py调用的待保鲜知识点列表"""
    full = scan_freshness(db_path)
    # 合并所有需要处理的，按紧急度排序
    items = (full["overdue_items"] +
             full["stale_items"] +
             full["due_7d_items"] +
             full["due_30d_items"])
    return items[:limit]


def print_report(result):
    """控制台打印保鲜扫描报告"""
    print("\n" + "=" * 60)
    print("  内容保鲜扫描报告")
    print("  扫描时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    tc = result["total_confirmed"]
    if tc == 0:
        print("\n  暂无已确认知识点，无需保鲜检查。")
        return

    print(f"\n  已确认知识点: {tc}条")
    print(f"  保鲜有效: {result['ok']}条")
    print(f"  待保鲜: {result['stale']}条 (其中逾期{result['overdue']}条)")
    print(f"  7天内到期: {result['due_7d']}条")
    print(f"  30天内到期: {result['due_30d']}条")

    if result.get("auto_filled", 0) > 0:
        print(f"\n  [自动补齐] 已为{result['auto_filled']}条知识点设置保鲜周期")

    # 逾期未检
    if result["overdue_items"]:
        print(f"\n{'─' * 50}")
        print(f"  !! 逾期未检 ({len(result['overdue_items'])}条) - 需要立即处理")
        print(f"{'─' * 50}")
        for item in result["overdue_items"][:20]:
            print(f"  #{item['id']} [{item['type']}] {item['title']}")
            print(f"       上次检查: {item['last_checked']} | 超期{item['days_overdue']}天")

    # 已到期
    if result["stale_items"]:
        print(f"\n{'─' * 50}")
        print(f"  >> 已到期 ({len(result['stale_items'])}条)")
        print(f"{'─' * 50}")
        for item in result["stale_items"][:20]:
            print(f"  #{item['id']} [{item['type']}] {item['title']}")
            print(f"       上次检查: {item['last_checked']} | 超期{item['days_overdue']}天")

    # 7天内到期
    if result["due_7d_items"]:
        print(f"\n{'─' * 50}")
        print(f"  > 7天内到期 ({len(result['due_7d_items'])}条)")
        print(f"{'─' * 50}")
        for item in result["due_7d_items"][:10]:
            print(f"  #{item['id']} [{item['type']}] {item['title']}  (还剩{item['days_remaining']}天)")

    # 30天内到期
    if result["due_30d_items"]:
        print(f"\n{'─' * 50}")
        print(f"  ~ 30天内到期 ({len(result['due_30d_items'])}条)")
        print(f"{'─' * 50}")
        for item in result["due_30d_items"][:10]:
            print(f"  #{item['id']} [{item['type']}] {item['title']}  (还剩{item['days_remaining']}天)")

    # 行动建议
    print(f"\n{'=' * 60}")
    print("  行动建议:")
    if result["overdue"] > 0 or result["stale"] > 0:
        print(f"  1. 打开审核界面，点击[保鲜筛选]按钮")
        print(f"  2. 逐条确认知识点是否仍然有效")
        print(f"  3. 过时的标记为已过时，有新版本的标记被替代")
    else:
        print(f"  当前所有知识点保鲜状态良好!")
    print("=" * 60)


def main():
    """命令行入口"""
    # 先执行v2.1.0-d迁移
    try:
        from scripts.migrate_v210d import migrate as migrate_d
    except ImportError:
        try:
            from migrate_v210d import migrate as migrate_d
        except ImportError:
            migrate_d = None

    if migrate_d:
        print("\n  检查数据库迁移状态...")
        try:
            migrate_d()
        except Exception as e:
            print(f"  [WARN] 迁移检查: {e}")

    result = scan_freshness()
    print_report(result)
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
