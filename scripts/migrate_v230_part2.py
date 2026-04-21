"""
migrate_v230_part2.py - v2.3.0 Part2 schema 迁移脚本
路径：scripts/migrate_v230_part2.py
版本：v2.3.0-part2

用途：
  为 F048 知识库体检 Agent 建两张新表：
    - health_reports        六维度体检报告
    - polish_suggestions    低分打磨建议

风格对齐 migrate_v223.py：
  - 幂等（PRAGMA 预检，两表都已存在直接跳过）
  - 支持 --dry-run（只打印 SQL 不执行）
  - 纯 schema 变更，不做任何数据迁移
  - 失败 rollback，不损坏既有 DB

用法：
  python scripts/migrate_v230_part2.py           # 实际执行
  python scripts/migrate_v230_part2.py --dry-run # 仅打印 SQL
  python scripts/migrate_v230_part2.py --db-path C:/path/to/knowledge_base.db

安全性说明：
  - 两张新表均不修改任何既有表
  - 两张新表完全独立（除 polish_suggestions.report_id 外键指向 health_reports）
  - 失败可安全重跑，已存在的表会被跳过
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


# ======================================================================
# SQL 语句（严格按 01 工程手册 v2.3.0 Part2 设计锁定章节）
# ======================================================================

SQL_CREATE_HEALTH_REPORTS = """
CREATE TABLE IF NOT EXISTS health_reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    total_score REAL,
    dim1_health_score REAL,
    dim2_structure_score REAL,
    dim3_processing_score REAL,
    dim4_relation_score REAL,
    dim5_polish_score REAL,
    dim6_monetize_score REAL,
    full_report_json TEXT,
    scanned_kp_count INTEGER,
    v3_call_count INTEGER,
    r1_call_count INTEGER,
    cost_estimate REAL,
    error_message TEXT
)
""".strip()

SQL_CREATE_POLISH_SUGGESTIONS = """
CREATE TABLE IF NOT EXISTS polish_suggestions (
    suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    kp_id INTEGER NOT NULL,
    diagnosis TEXT,
    suggestion_type TEXT,
    tier TEXT,
    original_content TEXT,
    suggested_content TEXT,
    status TEXT DEFAULT 'pending',
    applied_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (report_id) REFERENCES health_reports(report_id)
)
""".strip()

SQL_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_health_created ON health_reports(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_polish_report ON polish_suggestions(report_id)",
    "CREATE INDEX IF NOT EXISTS idx_polish_status ON polish_suggestions(status)",
]


# ======================================================================
# 辅助函数
# ======================================================================

def _table_exists(conn, table_name):
    """检查表是否存在"""
    c = conn.cursor()
    c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return c.fetchone() is not None


def _resolve_db_path(override=None):
    """按优先级解析 DB 路径：CLI 参数 > config/settings.json > 默认路径"""
    if override:
        return override
    import json as _json
    cfg = PROJECT_ROOT / "config" / "settings.json"
    if cfg.exists():
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                data = _json.load(f)
            db_path = data.get("database_path", "")
            if db_path:
                return db_path
        except Exception:
            pass
    return str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")


# ======================================================================
# 核心迁移逻辑
# ======================================================================

def run_migration(db_path, dry_run=False):
    """
    执行迁移。幂等：两表都已存在时直接退出。

    返回：
      0 - 成功（新建表或已是目标 schema）
      1 - 失败
    """
    print("=" * 60)
    print("v2.3.0 Part2 schema 迁移")
    print("  数据库路径: {}".format(db_path))
    print("  模式: {}".format("DRY-RUN（只打印 SQL 不执行）" if dry_run else "实际执行"))
    print("=" * 60)

    if not os.path.exists(db_path):
        print("[错误] 数据库文件不存在: {}".format(db_path))
        print("       如果是初次部署，请先跑 scripts/setup.py 建基础表")
        return 1

    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        print("[错误] 无法连接数据库: {}".format(e))
        return 1

    try:
        # 1. 预检：两表是否都已存在
        has_health = _table_exists(conn, "health_reports")
        has_polish = _table_exists(conn, "polish_suggestions")

        print("\n[预检]")
        print("  health_reports     : {}".format("已存在" if has_health else "不存在"))
        print("  polish_suggestions : {}".format("已存在" if has_polish else "不存在"))

        if has_health and has_polish:
            print("\n[跳过] 两张表均已存在，当前 DB 已是 v2.3.0-part2 schema")
            print("       （幂等：本脚本可安全重复执行）")
            return 0

        # 2. 打印/执行建表 SQL
        sqls = []
        if not has_health:
            sqls.append(("health_reports 表", SQL_CREATE_HEALTH_REPORTS))
        if not has_polish:
            sqls.append(("polish_suggestions 表", SQL_CREATE_POLISH_SUGGESTIONS))
        for idx_sql in SQL_CREATE_INDEXES:
            # 用 IF NOT EXISTS 重跑索引是安全的（即使表已存在）
            sqls.append(("索引", idx_sql))

        print("\n[执行 SQL]")
        if dry_run:
            for label, sql in sqls:
                print("\n  -- {} --".format(label))
                print("  " + sql.replace("\n", "\n  "))
            print("\n[DRY-RUN 完成] 以上 SQL 未实际执行")
            return 0

        # 真实执行（单事务）
        conn.execute("BEGIN")
        try:
            for label, sql in sqls:
                print("  执行: {}".format(label))
                conn.execute(sql)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print("\n[错误] 执行失败，已回滚: {}".format(e))
            return 1

        # 3. 验证
        print("\n[验证]")
        has_health_after = _table_exists(conn, "health_reports")
        has_polish_after = _table_exists(conn, "polish_suggestions")
        print("  health_reports     : {}".format("OK" if has_health_after else "FAIL"))
        print("  polish_suggestions : {}".format("OK" if has_polish_after else "FAIL"))

        if not (has_health_after and has_polish_after):
            print("\n[错误] 验证失败：建表后仍未找到目标表")
            return 1

        print("\n[成功] v2.3.0-part2 schema 迁移完成")
        return 0

    finally:
        conn.close()


# ======================================================================
# CLI 入口
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description="v2.3.0 Part2 schema 迁移（F048 知识库体检 Agent 基础层）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印 SQL 不执行（用于预览建表语句）",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="指定 DB 路径（默认读取 config/settings.json 或 data/database/knowledge_base.db）",
    )
    args = parser.parse_args()

    db_path = _resolve_db_path(args.db_path)
    return run_migration(db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
