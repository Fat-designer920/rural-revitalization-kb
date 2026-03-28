"""
migrate_v210d.py - v2.1.0-d 数据库迁移脚本
路径：scripts/migrate_v210d.py

迁移内容：
    knowledge_points 表新增: freshness_note (续期备注)

使用方法：保鲜检查.bat 和 一键提取.bat 启动时自动检测并执行，无需手动运行
"""

import sqlite3
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def get_db_path():
    config_path = PROJECT_ROOT / "config" / "settings.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            return config.get("database_path", str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db"))
    return str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")


def check_column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def migrate():
    db_path = get_db_path()
    if not Path(db_path).exists():
        print("  数据库不存在，跳过迁移（初始化时会自动创建新结构）")
        return True

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    migrated = []

    # --- knowledge_points 新增字段 ---
    if not check_column_exists(c, "knowledge_points", "freshness_note"):
        c.execute("ALTER TABLE knowledge_points ADD COLUMN freshness_note TEXT DEFAULT ''")
        migrated.append("knowledge_points.freshness_note")

    if migrated:
        conn.commit()
        print(f"  [迁移完成] 新增{len(migrated)}个字段: {', '.join(migrated)}")
    else:
        print(f"  [迁移检查] 数据库结构已是最新，无需迁移")

    conn.close()
    return True


if __name__ == "__main__":
    print("\n  v2.1.0-d 数据库迁移")
    print("  " + "=" * 40)
    try:
        migrate()
    except Exception as e:
        print(f"  [ERROR] 迁移失败: {e}")
    input("\n按回车键退出...")
