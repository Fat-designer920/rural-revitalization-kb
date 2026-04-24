# -*- coding: utf-8 -*-
"""
v2.3.1 迁移脚本:承受成熟度完整版 + 精品资产生产线
==================================================

作用:给已部署的老库追加 v2.3.1 新增的 schema(7 字段 + 1 表 + 3 索引)

幂等性:本脚本可重复执行,每次都先 PRAGMA table_info 检查字段是否存在再 ALTER。
       新表/索引走 CREATE TABLE/INDEX IF NOT EXISTS,天然幂等。

执行时机:v2.3.1 部署后,老唐手动跑一次:
    python scripts/migrate_v2_3_1.py [db_path]

    默认 db_path = ./data/rural_revitalization.db(相对项目根目录)

不需要执行的情况:
    1. 全新安装(首次安装.bat 会跑 setup.py 一次建好所有 schema)
    2. api_server 启动时的 db.init_tables() 兜底也会自动追字段和表
       (立规则第 8 条: api_server 启动兜底 init_tables)

但为了透明、可控、可审计,**建议老唐在升级到 v2.3.1 后手动执行一次本脚本**:
    - 备份先做(operation_hook 不适用升级脚本,请手动 copy 一份 .db)
    - 跑完脚本看输出,确认"7/7 字段追加"" 1/1 新表创建"" 3/3 索引创建"
    - 后续退役:v2.3.2 发布后本脚本可从代码树移除(立规则第 1 条)

立规则对齐:
    第 1 条:schema 单一真相,migrate 只服务老库追齐,用完退役
    第 6 条:ALTER 前 PRAGMA 检查字段存在,防重跑报错
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from pathlib import Path


# --- 待追加的 knowledge_points 字段(7 个)---
# 格式: (字段名, 完整 ALTER 子句)
#       CHECK 约束在 ALTER 里无法加,只能靠新库 CREATE TABLE 自带
#       老库 ALTER 追加的字段不带 CHECK,值的合法性由应用层保证
KP_NEW_COLUMNS = [
    ("premium_client",             "INTEGER DEFAULT 0"),
    ("premium_rfp",                "INTEGER DEFAULT 0"),
    ("premium_tier",               "TEXT DEFAULT NULL"),
    ("used_count",                 "INTEGER DEFAULT 0"),
    ("last_used_at",               "TEXT DEFAULT NULL"),
    ("used_for",                   "TEXT DEFAULT NULL"),
    ("premium_freshness_status",   "TEXT DEFAULT NULL"),
]

# --- 待创建的新表(1 张)---
NEW_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS premium_ai_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kp_id INTEGER NOT NULL,
    view TEXT NOT NULL CHECK(view IN ('client','rfp')),
    recommendation TEXT NOT NULL
        CHECK(recommendation IN ('strong','optional','not')),
    reason TEXT DEFAULT '',
    score REAL DEFAULT 0.0,
    source TEXT DEFAULT 'ai'
        CHECK(source IN ('ai','rule_fallback')),
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (kp_id) REFERENCES knowledge_points(id),
    UNIQUE(kp_id, view)
)
"""

# --- 待创建的索引(3 个)---
NEW_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_kp_premium_client ON knowledge_points(premium_client)",
    "CREATE INDEX IF NOT EXISTS idx_kp_premium_rfp ON knowledge_points(premium_rfp)",
    "CREATE INDEX IF NOT EXISTS idx_premium_cache_kp_view ON premium_ai_cache(kp_id, view)",
]


def _existing_columns(conn, table):
    """取表的已有字段名列表。表不存在时返回 None。"""
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if not c.fetchone():
        return None
    c.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in c.fetchall()]


def _existing_indexes(conn):
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='index'")
    return set(r[0] for r in c.fetchall())


def run_migration(db_path):
    """主入口。幂等执行。返回摘要 dict。"""
    if not os.path.exists(db_path):
        print(f"[错误] 数据库文件不存在: {db_path}")
        print("      如果是首次安装,请跑 首次安装.bat(内部调用 setup.py)")
        return {"ok": False, "error": "db_not_found"}

    print(f"[迁移启动] 目标数据库: {db_path}")
    print(f"[迁移启动] 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    summary = {
        "ok": True,
        "db_path": db_path,
        "columns_added": [],
        "columns_skipped": [],
        "tables_created": [],
        "tables_skipped": [],
        "indexes_created": [],
        "indexes_skipped": [],
    }

    # ============== Step 1: knowledge_points 字段追加 ==============
    print("\n[Step 1/3] knowledge_points 字段追加(7 个)")
    existing_kp_cols = _existing_columns(conn, "knowledge_points")
    if existing_kp_cols is None:
        print("  [错误] knowledge_points 表不存在,数据库结构异常")
        conn.close()
        summary["ok"] = False
        summary["error"] = "knowledge_points_table_missing"
        return summary

    for col_name, col_def in KP_NEW_COLUMNS:
        if col_name in existing_kp_cols:
            print(f"  [跳过] {col_name:30s} 已存在")
            summary["columns_skipped"].append(col_name)
        else:
            try:
                conn.execute(f"ALTER TABLE knowledge_points ADD COLUMN {col_name} {col_def}")
                print(f"  [追加] {col_name:30s} {col_def}")
                summary["columns_added"].append(col_name)
            except Exception as e:
                print(f"  [失败] {col_name:30s} {e}")
                summary["ok"] = False
                summary.setdefault("errors", []).append(f"ALTER {col_name}: {e}")

    # ============== Step 2: premium_ai_cache 表创建 ==============
    print("\n[Step 2/3] premium_ai_cache 新表")
    existing_cache = _existing_columns(conn, "premium_ai_cache")
    if existing_cache is not None:
        print(f"  [跳过] premium_ai_cache 已存在(字段数 {len(existing_cache)})")
        summary["tables_skipped"].append("premium_ai_cache")
    else:
        try:
            conn.executescript(NEW_TABLE_SQL)
            print(f"  [创建] premium_ai_cache")
            summary["tables_created"].append("premium_ai_cache")
        except Exception as e:
            print(f"  [失败] premium_ai_cache: {e}")
            summary["ok"] = False
            summary.setdefault("errors", []).append(f"CREATE TABLE premium_ai_cache: {e}")

    # ============== Step 3: 索引创建 ==============
    print("\n[Step 3/3] 索引创建(3 个)")
    existing_idx = _existing_indexes(conn)
    for idx_sql in NEW_INDEXES:
        # 从 SQL 里抠索引名
        #   "CREATE INDEX IF NOT EXISTS idx_xxx ON table(col)"
        idx_name = idx_sql.split("IF NOT EXISTS")[1].strip().split(" ")[0]
        if idx_name in existing_idx:
            print(f"  [跳过] {idx_name:40s} 已存在")
            summary["indexes_skipped"].append(idx_name)
        else:
            try:
                conn.execute(idx_sql)
                print(f"  [创建] {idx_name}")
                summary["indexes_created"].append(idx_name)
            except Exception as e:
                print(f"  [失败] {idx_name}: {e}")
                summary["ok"] = False
                summary.setdefault("errors", []).append(f"INDEX {idx_name}: {e}")

    conn.commit()
    conn.close()

    # ============== 汇总 ==============
    print("\n" + "=" * 60)
    print("[迁移完成]")
    print(f"  字段追加: {len(summary['columns_added'])} / 跳过: {len(summary['columns_skipped'])}")
    print(f"  新表创建: {len(summary['tables_created'])} / 跳过: {len(summary['tables_skipped'])}")
    print(f"  索引创建: {len(summary['indexes_created'])} / 跳过: {len(summary['indexes_skipped'])}")
    if not summary["ok"]:
        print(f"  [警告] 有失败项:{summary.get('errors', [])}")
    else:
        print(f"  全部成功")
    print("=" * 60)

    return summary


def _resolve_default_db_path():
    """复用 DatabaseManager 的路径解析逻辑,避免脚本路径假设和业务代码脱节
    (立规则第 9 条应验:不猜真实路径,直接复用 db 层逻辑).

    解析优先级(与 DatabaseManager.__init__ 完全一致):
      1. config/settings.json 里的 database_path 字段
      2. 兜底 PROJECT_ROOT/data/database/knowledge_base.db
    """
    project_root = Path(__file__).parent.parent
    # [优先 1] settings.json
    config_path = project_root / "config" / "settings.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            configured = config.get("database_path", "")
            if configured:
                return configured
        except Exception as e:
            print(f"[警告] settings.json 解析失败({e}),回退到兜底路径")
    # [兜底] PROJECT_ROOT/data/database/knowledge_base.db
    return str(project_root / "data" / "database" / "knowledge_base.db")


def main():
    # 默认 db 路径复用 DatabaseManager 的解析逻辑
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
        print(f"[提示] 使用命令行指定的 db 路径: {db_path}")
    else:
        db_path = _resolve_default_db_path()
        print(f"[提示] 使用 DatabaseManager 默认路径(与业务代码一致): {db_path}")

    result = run_migration(db_path)
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
