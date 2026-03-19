"""
migrate_v101_to_v110.py - 数据库迁移脚本
从 v1.0.1 升级到 v1.1.0
新增: edit_history表（编辑历史记录）
路径：scripts/migrate_v101_to_v110.py
"""
import sqlite3
import os
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def get_db_path():
    config_path = PROJECT_ROOT / "config" / "settings.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        db_path = config.get("database_path", "")
        if db_path:
            return db_path
    return str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")


def migrate():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"  [ERROR] 数据库文件不存在: {db_path}")
        print(f"  请先运行「初始化系统.bat」创建数据库")
        return False

    print(f"  数据库路径: {db_path}")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 检查edit_history表是否已存在
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='edit_history'")
    if c.fetchone():
        print(f"  [OK] edit_history表已存在，无需重复创建")
    else:
        print(f"  正在创建 edit_history 表...")
        c.execute("""CREATE TABLE IF NOT EXISTS edit_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_point_id INTEGER NOT NULL,
            edited_fields TEXT NOT NULL DEFAULT '{}',
            edit_summary TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_eh_kpid ON edit_history(knowledge_point_id)")
        print(f"  [OK] edit_history 表创建成功")

    # 检查architecture_suggestions表是否需要补字段（suggestion_type）
    c.execute("PRAGMA table_info(architecture_suggestions)")
    columns = [row[1] for row in c.fetchall()]
    if "suggestion_type" not in columns:
        print(f"  正在为 architecture_suggestions 表添加 suggestion_type 字段...")
        c.execute("ALTER TABLE architecture_suggestions ADD COLUMN suggestion_type TEXT DEFAULT 'add_level2'")
        print(f"  [OK] suggestion_type 字段添加成功")
    else:
        print(f"  [OK] suggestion_type 字段已存在")

    conn.commit()
    conn.close()

    print(f"\n  迁移完成！数据库已升级到 v1.1.0 结构")
    return True


if __name__ == "__main__":
    print(f"{'=' * 60}")
    print(f"  乡村振兴知识库 - 数据库迁移 v1.0.1 -> v1.1.0")
    print(f"{'=' * 60}")
    success = migrate()
    if not success:
        print(f"\n  迁移失败，请检查上面的错误信息")
    input("\n按回车键退出...")
