"""
migrate_v223.py - v2.2.3 hotfix 数据库迁移脚本
路径：scripts/migrate_v223.py
用途：把 v2.2.2 之前的数据库 schema 升级到 v2.2.3

核心原则：
  1. 纯 schema 变更，不做任何数据迁移/改写（全量重跑策略，历史数据会被清空重建）
  2. 幂等设计：重复运行不报错，字段已存在则跳过
  3. 操作前不做备份（老唐在批量重跑前会整体备份；本脚本只改schema）

变更项：
  source_files 表新增 3 字段：
    - truncation_count INTEGER DEFAULT 0
    - recovery_runs INTEGER DEFAULT 0
    - last_recovery_at TEXT
  knowledge_points 表新增 1 字段：
    - qa_source TEXT DEFAULT 'batch'
  新建表：operation_events（含 3 个索引）

使用：
  python scripts/migrate_v223.py           # 运行迁移
  python scripts/migrate_v223.py --dry-run # 仅检查，不执行

执行后：
  - 老唐走 v2.2.3 的批量重跑（F059）清空历史污染数据
  - 新提取的数据会自动写入新字段（qa_source / truncation_count 等）
"""
import os
import sys
import sqlite3
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def get_db_path():
    """读取 config/settings.json 中的 database_path，兜底用默认路径"""
    import json
    config_path = PROJECT_ROOT / "config" / "settings.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            p = config.get("database_path", "")
            if p and os.path.exists(p):
                return p
        except Exception:
            pass
    return str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")


def column_exists(conn, table, column):
    """检查表中是否已存在指定字段"""
    c = conn.cursor()
    try:
        c.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in c.fetchall()]
        return column in cols
    except Exception:
        return False


def table_exists(conn, table):
    """检查表是否存在"""
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return c.fetchone() is not None


def index_exists(conn, idx_name):
    """检查索引是否已存在"""
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (idx_name,))
    return c.fetchone() is not None


# --------------------------------------------------
# 各项迁移操作（每个都返回 (is_migrated, message)）
# --------------------------------------------------

def migrate_source_files(conn, dry_run=False):
    """source_files 表新增 3 个截断追溯字段"""
    results = []
    fields = [
        ("truncation_count", "INTEGER DEFAULT 0"),
        ("recovery_runs", "INTEGER DEFAULT 0"),
        ("last_recovery_at", "TEXT DEFAULT NULL"),
    ]
    for field_name, field_def in fields:
        if column_exists(conn, "source_files", field_name):
            results.append((False, f"  [跳过] source_files.{field_name} 已存在"))
            continue
        sql = f"ALTER TABLE source_files ADD COLUMN {field_name} {field_def}"
        if dry_run:
            results.append((False, f"  [dry-run] 将执行: {sql}"))
        else:
            try:
                conn.execute(sql)
                results.append((True, f"  [新增] source_files.{field_name}"))
            except Exception as e:
                results.append((False, f"  [失败] source_files.{field_name}: {e}"))
    return results


def migrate_knowledge_points(conn, dry_run=False):
    """knowledge_points 表新增 qa_source 字段"""
    results = []
    if column_exists(conn, "knowledge_points", "qa_source"):
        results.append((False, "  [跳过] knowledge_points.qa_source 已存在"))
        return results
    sql = "ALTER TABLE knowledge_points ADD COLUMN qa_source TEXT DEFAULT 'batch'"
    if dry_run:
        results.append((False, f"  [dry-run] 将执行: {sql}"))
    else:
        try:
            conn.execute(sql)
            results.append((True, "  [新增] knowledge_points.qa_source"))
        except Exception as e:
            results.append((False, f"  [失败] knowledge_points.qa_source: {e}"))
    return results


def migrate_operation_events(conn, dry_run=False):
    """新建 operation_events 表及索引"""
    results = []

    if table_exists(conn, "operation_events"):
        results.append((False, "  [跳过] operation_events 表已存在"))
    else:
        create_sql = """
        CREATE TABLE operation_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            event_type TEXT NOT NULL,
            module TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info'
                CHECK(severity IN ('info','warning','error')),
            related_file_id INTEGER,
            related_kp_id INTEGER,
            payload_json TEXT DEFAULT '{}',
            FOREIGN KEY (related_file_id) REFERENCES source_files(id),
            FOREIGN KEY (related_kp_id) REFERENCES knowledge_points(id)
        )
        """
        if dry_run:
            results.append((False, "  [dry-run] 将建表 operation_events"))
        else:
            try:
                conn.execute(create_sql)
                results.append((True, "  [新建表] operation_events"))
            except Exception as e:
                results.append((False, f"  [失败] operation_events 建表: {e}"))

    # 索引
    indexes = [
        ("idx_events_time", "CREATE INDEX idx_events_time ON operation_events(event_time)"),
        ("idx_events_type", "CREATE INDEX idx_events_type ON operation_events(event_type)"),
        ("idx_events_file", "CREATE INDEX idx_events_file ON operation_events(related_file_id)"),
    ]
    for idx_name, idx_sql in indexes:
        if index_exists(conn, idx_name):
            results.append((False, f"  [跳过] 索引 {idx_name} 已存在"))
            continue
        if dry_run:
            results.append((False, f"  [dry-run] 将创建索引 {idx_name}"))
        else:
            try:
                conn.execute(idx_sql)
                results.append((True, f"  [新增索引] {idx_name}"))
            except Exception as e:
                results.append((False, f"  [失败] 索引 {idx_name}: {e}"))
    return results


# --------------------------------------------------
# 主流程
# --------------------------------------------------

def run_migrate(db_path=None, dry_run=False):
    """执行 v2.2.3 迁移"""
    if db_path is None:
        db_path = get_db_path()

    print("")
    print("=" * 60)
    print("  乡村振兴知识库 - v2.2.3 数据库迁移")
    print("=" * 60)
    print("")
    print("  数据库: {}".format(db_path))
    print("  模式: {}".format("DRY-RUN（仅检查不执行）" if dry_run else "正式执行"))
    print("")

    if not os.path.exists(db_path):
        print("[错误] 数据库文件不存在，请先完成首次部署（运行 首次安装.bat）")
        return False

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")

    total_migrated = 0
    total_skipped = 0
    total_failed = 0

    print("[1/3] source_files 表字段迁移")
    print("-" * 60)
    for migrated, msg in migrate_source_files(conn, dry_run):
        print(msg)
        if migrated:
            total_migrated += 1
        elif "失败" in msg:
            total_failed += 1
        elif "跳过" in msg:
            total_skipped += 1
    print("")

    print("[2/3] knowledge_points 表字段迁移")
    print("-" * 60)
    for migrated, msg in migrate_knowledge_points(conn, dry_run):
        print(msg)
        if migrated:
            total_migrated += 1
        elif "失败" in msg:
            total_failed += 1
        elif "跳过" in msg:
            total_skipped += 1
    print("")

    print("[3/3] operation_events 表与索引迁移")
    print("-" * 60)
    for migrated, msg in migrate_operation_events(conn, dry_run):
        print(msg)
        if migrated:
            total_migrated += 1
        elif "失败" in msg:
            total_failed += 1
        elif "跳过" in msg:
            total_skipped += 1
    print("")

    if not dry_run:
        conn.commit()
    conn.close()

    print("=" * 60)
    print("  迁移完成")
    print("=" * 60)
    print("  新增项:  {}".format(total_migrated))
    print("  已存在:  {}".format(total_skipped))
    print("  失败项:  {}".format(total_failed))
    print("")

    if total_failed > 0:
        print("[警告] 有迁移项失败，请检查上方错误信息")
        return False

    if dry_run:
        print("[提示] Dry-run 完成，正式迁移请去掉 --dry-run 参数重新运行")
    else:
        print("[成功] v2.2.3 schema 已就绪")
        print("")
        print("  下一步：")
        print("  1. 批量重跑前会自动备份（F060 operation_hook）")
        print("  2. 通过工具箱 > 批量重跑 清空历史污染数据并重新提取（F059）")
        print("  3. 新提取的知识点会自动写入 qa_source 字段（F058质检降级）")
        print("  4. R1 截断时自动触发补救并记录 truncation_count（F057）")

    return total_failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="v2.2.3 数据库 schema 迁移")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅检查迁移项，不实际执行 ALTER/CREATE")
    parser.add_argument("--db", type=str, default=None,
                        help="指定数据库路径（默认从 config/settings.json 读取）")
    args = parser.parse_args()

    ok = run_migrate(db_path=args.db, dry_run=args.dry_run)

    # 便携版交互：双击运行后按回车退出
    if sys.stdin.isatty():
        print("")
        try:
            input("按回车键退出...")
        except EOFError:
            pass

    sys.exit(0 if ok else 1)
